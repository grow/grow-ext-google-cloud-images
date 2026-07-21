"""ext-cloud-images backend.

Migrated from the legacy App Engine Python 2.7 runtime to Python 3. The Images
and Blobstore APIs are still provided through the App Engine bundled services
(via `appengine-python-standard`), request routing uses Flask, and Google Cloud
Storage access uses the `google-cloud-storage` client library (the legacy
`cloudstorage` client is not available on Python 3).
"""

import json
import logging
import mimetypes
import os
import uuid

import flask
import requests
from google.appengine.api import images
from google.appengine.api import wrap_wsgi_app
from google.appengine.ext import blobstore
from google.cloud import exceptions as gcs_exceptions
from google.cloud import storage

APPID = os.environ.get('GOOGLE_CLOUD_PROJECT', '')
BUCKET_NAME = '{}.appspot.com'.format(APPID)
FOLDER = 'grow-ext-cloud-images-uploads'
SERVICE_ACCOUNT_EMAIL = '{}@appspot.gserviceaccount.com'.format(APPID)

IMAGE_EXTENSIONS = (
    '.gif',
    '.jpeg',
    '.jpg',
    '.png',
    '.webp',
)

BLOB_EXTENSIONS = (
    '.json',
    '.mp4',
    '.svg',
    '.webm',
)

# Timeout (in seconds) for the anonymous public-readability check.
PUBLIC_READ_CHECK_TIMEOUT = 10

app = flask.Flask(__name__)
# Enable access to the App Engine bundled services (Images, Blobstore, etc.).
app.wsgi_app = wrap_wsgi_app(app.wsgi_app)

_storage_client = None


def get_storage_client():
    """Returns a lazily-initialized Cloud Storage client."""
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client()
    return _storage_client


def split_bucket_path(path):
    """Splits a `/bucket/object/name` path into (bucket, object) parts."""
    parts = path.lstrip('/').split('/', 1)
    bucket_name = parts[0]
    blob_name = parts[1] if len(parts) > 1 else ''
    return bucket_name, blob_name


def gcs_stat(path):
    """Returns the GCS blob at `path`, raising NotFound if it does not exist."""
    bucket_name, blob_name = split_bucket_path(path)
    blob = get_storage_client().bucket(bucket_name).get_blob(blob_name)
    if blob is None:
        raise gcs_exceptions.NotFound(path)
    return blob


def _apply_metadata(blob, metadata):
    """Applies a legacy cloudstorage-style metadata dict to a GCS blob."""
    custom = dict(blob.metadata or {})
    changed_custom = False
    for key, value in metadata.items():
        lowered = key.lower()
        if lowered == 'cache-control':
            blob.cache_control = value
        elif lowered == 'content-type':
            blob.content_type = value
        elif lowered.startswith('x-goog-meta-'):
            custom[key[len('x-goog-meta-'):]] = value
            changed_custom = True
        else:
            custom[key] = value
            changed_custom = True
    if changed_custom:
        blob.metadata = custom


def gcs_copy(src_path, dst_path, metadata=None):
    """Copies a GCS object, optionally updating metadata on the destination."""
    src_bucket_name, src_blob_name = split_bucket_path(src_path)
    dst_bucket_name, dst_blob_name = split_bucket_path(dst_path)
    client = get_storage_client()
    src_bucket = client.bucket(src_bucket_name)
    dst_bucket = client.bucket(dst_bucket_name)
    src_blob = src_bucket.blob(src_blob_name)
    new_blob = src_bucket.copy_blob(src_blob, dst_bucket, dst_blob_name)
    if metadata:
        _apply_metadata(new_blob, metadata)
        new_blob.patch()
    return new_blob


def gcs_write_public(path, data, content_type):
    """Writes `data` to `path` in GCS with a public-read ACL."""
    bucket_name, blob_name = split_bucket_path(path)
    blob = get_storage_client().bucket(bucket_name).blob(blob_name)
    blob.upload_from_string(
        data, content_type=content_type, predefined_acl='publicRead')
    return blob


def _created_timestamp(blob):
    """Returns the blob creation time as an epoch float (or None)."""
    if blob.time_created:
        return blob.time_created.timestamp()
    return None


def is_publicly_readable(bucket_path):
    """Returns whether a GCS object is anonymously (publicly) readable.

    The service processes requests using a privileged service account that has
    read access to many buckets. Without this check, an unauthenticated caller
    could ask the service to read an IAM-restricted object and re-serve it
    publicly, bypassing GCS access controls. By requiring the source object to
    already be anonymously readable, the service can only ever expose content
    that is already public.
    """
    url = 'https://storage.googleapis.com/{}'.format(bucket_path.lstrip('/'))
    try:
        # This request is unauthenticated (no service account credentials are
        # attached), so it reflects true public accessibility of the object.
        resp = requests.head(url, timeout=PUBLIC_READ_CHECK_TIMEOUT)
    except Exception:
        logging.exception(
            'Error checking public access for {}'.format(bucket_path))
        return False
    return resp.status_code == 200


def _json_response(payload, status=200):
    return flask.Response(
        json.dumps(payload), status=status, mimetype='application/json')


@app.route('/callback', methods=['POST'])
def upload_callback():
    upload_handler = blobstore.BlobstoreUploadHandler()
    uploaded_files = upload_handler.get_uploads(flask.request.environ, 'file')
    blob_info = uploaded_files[0]
    blob_key = blob_info.key()
    url = images.get_serving_url(blob_key, secure_url=True)
    resp = _json_response({'url': url})
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@app.route('/upload', methods=['GET'])
@app.route('/upload/<path:bucket>', methods=['GET'])
def upload(bucket=None):
    bucket = bucket or BUCKET_NAME
    gs_bucket_name = '{}/{}'.format(bucket, FOLDER)
    action = blobstore.create_upload_url(
        '/callback', gs_bucket_name=gs_bucket_name)
    return flask.render_template(
        'upload.html', bucket=gs_bucket_name, action=action)


@app.route('/_api/create_upload_url', methods=['GET'])
@app.route('/_api/create_upload_url/<path:bucket>', methods=['GET'])
def create_upload_url(bucket=None):
    bucket = bucket or BUCKET_NAME
    gs_bucket_name = '{}/{}'.format(bucket, FOLDER)
    upload_url = blobstore.create_upload_url(
        '/callback', gs_bucket_name=gs_bucket_name)
    return _json_response({'upload_url': upload_url})


@app.route('/_api/upload_file', methods=['POST'])
@app.route('/_api/upload_file/<path:bucket>', methods=['POST'])
def upload_file_on_server(bucket=None):
    bucket = bucket or BUCKET_NAME
    uploaded = flask.request.files.get('file')
    if uploaded is None:
        return _json_response({'error': "'file'"}, status=400)
    uploaded_content = uploaded.read()
    uploaded_name = uploaded.filename
    name, ext = os.path.splitext(uploaded_name)
    request_hash = os.getenv('REQUEST_ID_HASH') or uuid.uuid4().hex
    hashed_name = '{}_{}{}'.format(name, request_hash, ext)
    gs_path = '/{}/{}/{}'.format(bucket, FOLDER, hashed_name)
    if hashed_name.endswith('.svg'):
        mimetype = 'image/svg+xml'
    else:
        mimetype = mimetypes.guess_type(hashed_name)[0]
    gcs_write_public(gs_path, uploaded_content, mimetype)
    blob_key = blobstore.create_gs_key('/gs{}'.format(gs_path))

    if gs_path.endswith(IMAGE_EXTENSIONS):
        serving_url = images.get_serving_url(blob_key, secure_url=True)
        result = {'url': serving_url}
        try:
            data = blobstore.fetch_data(blob_key, 0, 50000)
            image = images.Image(image_data=data)
            result.update({
                'gs_path': gs_path,
                'height': image.height,
                'width': image.width,
            })
        except images.BadImageError:
            # If the header containing sizes isn't in the first 50000 bytes of
            # the image. Or, if the file uploaded was just not a real image.
            logging.exception('Failed to transform image.')
    else:
        serving_url = 'https://storage.googleapis.com{}'.format(gs_path)
        result = {
            'url': serving_url,
        }
    return _json_response(result)


def normalize_gs_path(gs_path, locale):
    gs_path = '/gs/{}'.format(gs_path.lstrip('/'))
    if '{locale}' not in gs_path:
        stat_result = gcs_stat(gs_path[3:])
        return gs_path, stat_result
    # Retrieve a localized image if it exists, otherwise strip the locale
    # placeholder from the path and return the base image.
    localized_gs_path = gs_path.replace('{locale}', locale)
    try:
        stat_result = gcs_stat(localized_gs_path[3:])
        return localized_gs_path, stat_result
    except (gcs_exceptions.NotFound, gcs_exceptions.Forbidden):
        # If no file exists for the full locale identifier (language and
        # territory), attempt retrieving a file for just the territory.
        if '_' in locale:
            language, territory = locale.split('_', 1)
            localized_gs_path = \
                gs_path.replace('{locale}', '_{}'.format(territory))
            try:
                stat_result = gcs_stat(localized_gs_path[3:])
                return localized_gs_path, stat_result
            except (gcs_exceptions.NotFound, gcs_exceptions.Forbidden):
                pass
    gs_path = gs_path.replace('@{locale}', '')
    stat_result = gcs_stat(gs_path[3:])
    return gs_path, stat_result


@app.route('/', defaults={'gs_path': ''}, methods=['GET'])
@app.route('/<path:gs_path>', methods=['GET'])
def get_serving_url(gs_path):
    gs_path = flask.request.args.get('gs_path') or gs_path
    reset_cache = flask.request.args.get('reset_cache', '')
    locale = flask.request.args.get('locale', '')
    if not gs_path:
        detail = (
            'Usage: Share GCS objects with `{}`. Make requests to:'
            ' {}://{}/<bucket>/<path>.ext'.format(
                SERVICE_ACCOUNT_EMAIL,
                flask.request.scheme,
                flask.request.host))
        flask.abort(400, description=detail)
    try:
        gs_path, stat_result = normalize_gs_path(gs_path, locale)
    except (gcs_exceptions.NotFound, gcs_exceptions.Forbidden):
        # Object does not exist (or is not accessible). Return a generic 404 so
        # a nonexistent path and a non-public path are indistinguishable.
        flask.abort(404)
    bucket_path = gs_path[3:]  # bucket/path.mp4

    # Only serve objects that are already anonymously (publicly) readable.
    # The service account has read access to many restricted buckets, so
    # without this check an unauthenticated caller could use this service as
    # an open proxy to read IAM-restricted objects and re-serve them
    # publicly. Legitimate assets served through this service are already
    # public, so this does not affect normal usage.
    if not is_publicly_readable(bucket_path):
        # Use a generic 404 that does not reveal whether the object exists or is
        # merely non-public, to avoid leaking GCS object names via prober-style
        # enumeration attacks.
        flask.abort(404)

    # Image-handling.
    if gs_path.endswith(IMAGE_EXTENSIONS):
        blob_key = blobstore.create_gs_key(gs_path)
        if reset_cache:
            try:
                images.delete_serving_url(blob_key)
            except images.Error as e:
                logging.error(
                    'Error deleting {} -> {}'.format(gs_path, str(e)))
        try:
            url = images.get_serving_url(blob_key, secure_url=True)
        except images.AccessDeniedError:
            flask.abort(
                400,
                description=(
                    'Ensure the following service account has access to the'
                    ' object in Google Cloud Storage: {}'.format(
                        SERVICE_ACCOUNT_EMAIL)))
        except images.ObjectNotFoundError:
            flask.abort(
                400,
                description=(
                    'The object was not found. Ensure the following service'
                    ' account has access to the object in Google Cloud'
                    ' Storage: {}'.format(SERVICE_ACCOUNT_EMAIL)))
        except images.TransformationError:
            # A TransformationError may happen in several scenarios - if
            # the file is simply too large for the images service to
            # handle, if the image service doesn't have access to the file,
            # or if the file was already uploaded to the image service by
            # another App Engine app. For the latter case, we can try to
            # work around that by copying the file and re-uploading it to
            # the image service.
            copied_bucket_path = bucket_path + '.copy'
            gcs_copy(bucket_path, copied_bucket_path)
            copied_gs_path = '/gs{}'.format(copied_bucket_path)
            blob_key = blobstore.create_gs_key(copied_gs_path)
            try:
                url = images.get_serving_url(blob_key, secure_url=True)
            except images.TransformationError:
                message = ('Failed to copy file to attempt to fix'
                           ' TransformationError -> {}')
                logging.error(message.format(copied_bucket_path))
                logging.exception('Debugging TransformationError.')
                flask.abort(
                    400,
                    description=(
                        'There was a problem transforming the image. Ensure'
                        ' the following service account has access to the'
                        ' object in Google Cloud Storage: {}'.format(
                            SERVICE_ACCOUNT_EMAIL)))

        image_metadata = {}
        try:
            data = blobstore.fetch_data(blob_key, 0, 50000)
            image = images.Image(image_data=data)
            image_metadata = {
                'height': image.height,
                'width': image.width,
            }
        except images.BadImageError:
            # If the header containing sizes isn't in the first 50000 bytes of
            # the image. Or, if the file uploaded was just not a real image.
            logging.exception('Failed to transform image.')
        response_content = json.dumps({
            'content_type': stat_result.content_type,
            'created': _created_timestamp(stat_result),
            'etag': stat_result.etag,
            'image_metadata': image_metadata,
            'metadata': stat_result.metadata,
            'size': stat_result.size,
            'url': url,
        })

    # Non-image (i.e. SVG, blob file) handling.
    else:
        video_metadata = {}
        ext = gs_path.split('.')[-1]  # mp4
        bucket = bucket_path.lstrip('/').split('/')[0]  # bucket
        basename = str(uuid.uuid4())
        blob_bucket_path = '/{}/blobs/{}.{}'.format(bucket, basename, ext)
        url = 'https://storage.googleapis.com{}'.format(blob_bucket_path)
        original_bucket_path = bucket_path
        if bucket_path.endswith('.svg'):
            mimetype = 'image/svg+xml'
        else:
            mimetype = mimetypes.guess_type(bucket_path)[0]
        metadata = {
            'Cache-Control': 'max-age=31536000',
            'x-goog-meta-optimized': 'true',
            'x-goog-meta-url': url,
        }
        if mimetype:
            metadata.update({'content-type': mimetype})
        try:
            stat_result = gcs_stat(blob_bucket_path)
            # Use the blob_bucket_path to support obfuscated mp4 files.
            bucket_path = blob_bucket_path
        except gcs_exceptions.NotFound:
            # Copy file to blob path.
            gcs_copy(bucket_path, blob_bucket_path, metadata=metadata)
            bucket_path = blob_bucket_path
        except gcs_exceptions.Forbidden:
            pass
        # Also ensure the original item's metadata is updated.
        gcs_copy(original_bucket_path, original_bucket_path, metadata=metadata)
        response_content = json.dumps({
            'content_type': stat_result.content_type,
            'created': _created_timestamp(stat_result),
            'etag': stat_result.etag,
            'image_metadata': video_metadata,
            'metadata': stat_result.metadata,
            'size': stat_result.size,
            'url': url,
        })

    return flask.Response(response_content, mimetype='application/json')


@app.errorhandler(404)
def handle_not_found(error):
    # Return an empty 404 body so that neither existence nor accessibility of a
    # GCS object can be inferred from the response.
    return flask.Response('', status=404)


@app.before_request
def handle_cors_preflight():
    if flask.request.method == 'OPTIONS':
        resp = flask.Response('', status=200)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = '*'
        resp.headers['Access-Control-Allow-Headers'] = \
            'origin, content-type, accept'
        return resp


@app.after_request
def add_cors_header(response):
    if 'Access-Control-Allow-Origin' not in response.headers:
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = '*'
        response.headers['Access-Control-Allow-Headers'] = \
            'origin, content-type, accept'
    return response


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
