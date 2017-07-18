from google.appengine.api import app_identity
from google.appengine.api import images
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext.webapp import template
import json
import logging
import os
import webapp2


APPID = app_identity.get_application_id()
BUCKET_NAME = app_identity.get_default_gcs_bucket_name()
FOLDER = 'grow-ext-cloud-images-uploads'


class UploadCallbackHandler(blobstore_handlers.BlobstoreUploadHandler):

    def post(self):
        uploaded_files = self.get_uploads('file')
        blob_info = uploaded_files[0]
        blob_key = blob_info.key()
        url = images.get_serving_url(blob_key, secure_url=True)
        self.redirect(url)


class UploadHandler(blobstore_handlers.BlobstoreUploadHandler):

    def get(self, bucket=None):
        bucket = bucket or BUCKET_NAME
        gs_bucket_name = '{}/{}'.format(bucket, FOLDER)
        action = blobstore.create_upload_url(
                '/callback', gs_bucket_name=gs_bucket_name)
        # Support for Cloudflare proxy.
        action = action.replace('http://', 'https://')
        kwargs = {
            'bucket': gs_bucket_name,
            'action': action,
        }
        self.response.out.write(template.render('upload.html', kwargs))


class GetServingUrlHandler(webapp2.RequestHandler):

    def get(self, gs_path):
        gs_path = self.request.get('gs_path') or gs_path
        service_account_email = \
            '{}@appspot.gserviceaccount.com'.format(APPID)
        if not gs_path:
            detail = (
                'Usage: Share GCS objects with `{}`. Make requests to:'
                ' {}://{}/<bucket>/<path>.ext'.format(
                    service_account_email,
                    os.getenv('wsgi.url_scheme'),
                    os.getenv('HTTP_HOST')))
            self.abort(400, detail=detail)
            return
        gs_path = '/gs/{}'.format(gs_path.lstrip('/'))
        try:
            blob_key = blobstore.create_gs_key(gs_path)
            url = images.get_serving_url(blob_key, secure_url=True)
        except images.AccessDeniedError:
            detail = (
                'Ensure the following service'
                ' account has access to the object in Google Cloud Storage:'
                ' {}'.format(service_account_email))
            self.abort(400, explanation='AccessDeniedError', detail=detail)
            return
        except images.ObjectNotFoundError:
            detail = (
                'The object was not found. Ensure the following service'
                ' account has access to the object in Google Cloud Storage:'
                ' {}'.format(service_account_email))
            self.abort(400, explanation='ObjectNotFoundError', detail=detail)
            return
        except (images.TransformationError, ValueError):
            logging.exception('Debugging TransformationError.')
            detail = (
                'There was a problem transforming the image. Ensure the'
                ' following service account has access to the object in Google'
                ' Cloud Storage: {}'.format(service_account_email))
            self.abort(400, explanation='TransformationError', detail=detail)
            return
        # TODO(jeremydw): This is a WIP.
        # Should be updated based on Grow's integration.
        if self.request.get('redirect'):
            size = self.request.get('size')
            if size:
                url += '=s{}'.format(size)
            self.redirect(url)
            return
        response_content = json.dumps({'url': url})
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(response_content)


app = webapp2.WSGIApplication([
  ('/callback', UploadCallbackHandler),
  ('/upload/(.*)', UploadHandler),
  ('/upload', UploadHandler),
  ('/(.*)', GetServingUrlHandler),
])
