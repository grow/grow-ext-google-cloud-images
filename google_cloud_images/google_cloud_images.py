from jinja2.ext import Extension
from protorpc import messages
import grow
import os
import jinja2
import requests


class Error(Exception):
    pass


__preprocessor = None


def _get_preprocessor(pod):
    global __preprocessor
    if __preprocessor:
        return __preprocessor
    for preprocessor in pod.list_preprocessors():
        if preprocessor.KIND == GoogleCloudImagesPreprocessor.KIND:
            __preprocessor = preprocessor
            return preprocessor


def get_placeholder(bucket_path, placeholders):
    _, ext = os.path.splitext(bucket_path)
    if ext not in placeholders:
        raise Error('No placeholder found for GCS path -> {}'.format(bucket_path))
    return placeholders.get(ext)


def get_image_serving_data(backend, bucket_path, locale=None, fuzzy_extensions=None, logger=None, placeholders=None, is_placeholder=False):
    """Makes a request to the backend microservice capable of generating URLs
    that use Google's image-serving infrastructure."""
    params = {'gs_path': bucket_path}
    if locale:
        params['locale'] = locale
    resp = requests.get(backend, params)
    try:
        return resp.json(), not is_placeholder
    except ValueError:
        if fuzzy_extensions:
            base, original_ext = os.path.splitext(bucket_path)
            if original_ext not in ['.jpg', '.png']:
                raise Error('Fuzzy extensions only supports .png and .jpg files.')
            new_ext = '.jpg' if original_ext == '.png' else '.png'
            bucket_path = base + new_ext
            if logger:
                logger.info('Trying fuzzy extension -> {}'.format(bucket_path))
            return get_image_serving_data(backend, bucket_path, locale=locale, fuzzy_extensions=False, logger=logger, placeholders=placeholders)
        if placeholders:
            if logger:
                logger.warning('Error with Google Cloud Images URL (using placeholder instead) -> {}'.format(bucket_path))
            placeholder_path = get_placeholder(bucket_path, placeholders)
            return get_image_serving_data(backend, placeholder_path, locale=locale, fuzzy_extensions=False, logger=logger, is_placeholder=True)
        text = 'An error occurred generating a Google Cloud Images URL for: {}'
        raise Error(text.format(bucket_path))


class GoogleImage(object):

    def __init__(self, pod, bucket_path, locale=None, original_locale=None, fuzzy_extensions=False):
        self.pod = pod
        self.locale = locale
        self.original_locale = original_locale
        self.bucket_path = bucket_path
        self._base_url = None
        self._backend = None
        self._placeholders = None
        self._fuzzy_extensions = fuzzy_extensions
        self._cache = None
        self.__data = None

    def __repr__(self):
        return '<GoogleImage {}>'.format(self.bucket_path)

    @property
    def cache(self):
        if self._cache is None:
            podcache = self.pod.podcache
            ident = 'ext-google-cloud-images'
            self._cache = podcache.get_object_cache(ident, write_to_file=True)
        return self._cache

    @property
    def placeholders(self):
        if self._placeholders is None:
            preprocessor = _get_preprocessor(self.pod)
            self._placeholders = preprocessor.extensions_to_placeholders()
        return self._placeholders

    @property
    def backend(self):
        if self._backend is None:
            preprocessor = _get_preprocessor(self.pod)
            self._backend = preprocessor.config.backend
        return self._backend

    @property
    def _data(self):
        if self.__data is None:
            image_serving_data = self.cache.get(self._cache_key)
            if image_serving_data is not None:
                self.__data = image_serving_data
            else:
                if self.locale and '{locale}' in self.bucket_path:
                    if self.locale != self.original_locale:
                        message = 'Generating Google Cloud Images data -> {} ({} for {})'
                        message = message.format(self.bucket_path, self.locale, self.original_locale)
                    else:
                        message = 'Generating Google Cloud Images data -> {} ({})'
                        message = message.format(self.bucket_path, self.locale)
                else:
                    message = 'Generating Google Cloud Images data -> {}'
                    message = message.format(self.bucket_path)
                self.pod.logger.info(message)
                data, use_cache = get_image_serving_data(self.backend, self.bucket_path,
                                              locale=self.locale,
                                              fuzzy_extensions=self._fuzzy_extensions,
                                              logger=self.pod.logger,
                                              placeholders=self.placeholders)
                if use_cache:
                    self.cache.add(self._cache_key, data)
                self.__data = data
        return self.__data

    @property
    def _cache_key(self):
        if '{locale}' in self.bucket_path:
            return '{}:{}:{}:metadata'.format(self.backend, self.bucket_path, self.locale)
        return '{}:{}:metadata'.format(self.backend, self.bucket_path)

    @property
    def base_url(self):
        """Returns a URL corresponding to the image served by Google's
        image-serving infrastructure."""
        if self._base_url is None:
            self._base_url = self._data['url']
        return self._base_url

    @property
    def content_type(self):
        return self._data['content_type']

    @property
    def created(self):
        return self._data['created']

    @property
    def dimensions(self):
        return '{}x{}'.format(self.width, self.height)

    @property
    def etag(self):
        return self._data['etag']

    @property
    def height(self):
        return self._data['image_metadata'].get('height')

    @property
    def size(self):
        return self._data['size']

    def url(self, options=None):
        if not options:
            return self.base_url
        return '{}={}'.format(self.base_url, '-'.join(options))

    @property
    def width(self):
        return self._data['image_metadata'].get('width')


class GoogleCloudImagesExtension(Extension):

    def __init__(self, environment):
        super(GoogleCloudImagesExtension, self).__init__(environment)
        environment.globals['google_image'] = \
            GoogleCloudImagesExtension.create_google_image

    @staticmethod
    @jinja2.contextfunction
    def create_google_image(ctx, bucket_path, fuzzy_extensions=False):
        if 'doc' not in ctx:
            raise Exception(
                'Missing `doc` in the template context. Are'
                ' you using `google_image` within a macro? Remember to {%'
                ' import ... with context %}.')
        doc = ctx['doc']
        pod = doc.pod
        locale = doc.locale
        # Supports aliasing one locale to another, for example we can say all
        # `es_PR` pages should use `en_US` assets.
        # Either pull the locale from a global rewrite from podspec, or pull
        # from a key `google_cloud_images_locale` on the document.
        if 'google_cloud_images_locale' in doc.fields and doc.google_cloud_images_locale:
            locale = doc.google_cloud_images_locale
        else:
            preprocessor = _get_preprocessor(doc.pod)
            if preprocessor.config.rewrite_locales:
                for rewrite_locales in preprocessor.config.rewrite_locales:
                    if locale == rewrite_locales.rewrite:
                        locale = rewrite_locales.to
        return GoogleImage(pod, bucket_path, locale=locale, original_locale=doc.locale,
                           fuzzy_extensions=fuzzy_extensions)


class RewriteLocalesMessage(messages.Message):
    rewrite = messages.StringField(1)
    to = messages.StringField(2)


class PlaceholderMessage(messages.Message):
    extensions = messages.StringField(1, repeated=True)
    path = messages.StringField(2)


class GoogleCloudImagesPreprocessor(grow.Preprocessor):
    KIND = 'google_cloud_images'
    _extensions_to_placeholders = None

    class Config(messages.Message):
        backend = messages.StringField(1)
        rewrite_locales = messages.MessageField(RewriteLocalesMessage, 2, repeated=True)
        placeholders = messages.MessageField(PlaceholderMessage, 3, repeated=True)

    def run(self, *args, **kwargs):
        text = 'Using Google Cloud images backend -> {}'
        message = text.format(self.config.backend)
        self.pod.logger.info(message)

    def extensions_to_placeholders(self):
        if self._extensions_to_placeholders is None:
            self._extensions_to_placeholders = {}
            if self.config.placeholders:
                for placeholder in self.config.placeholders:
                    for ext in placeholder.extensions:
                        self._extensions_to_placeholders[ext] = placeholder.path
        return self._extensions_to_placeholders
