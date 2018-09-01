from jinja2.ext import Extension
from protorpc import messages
import grow
import os
import jinja2
import requests


class Error(Exception):
    pass


def get_image_serving_data(backend, bucket_path, locale=None, fuzzy_extensions=None):
    """Makes a request to the backend microservice capable of generating URLs
    that use Google's image-serving infrastructure."""
    params = {'gs_path': bucket_path}
    if locale:
        params['locale'] = locale
    resp = requests.get(backend, params)
    try:
        return resp.json()
    except ValueError:
        if fuzzy_extensions:
            base, original_ext = os.path.splitext(bucket_path)
            if original_ext not in ['.jpg', '.png']:
                raise Error('Fuzzy extensions only supports .png and .jpg files.')
            new_ext = '.jpg' if original_ext == '.png' else '.png'
            bucket_path = os.path.join(base, new_ext)
            logging.info('Trying fuzzy extension -> {}'.format(bucket_path))
            return get_image_serving_data(backend, bucket_path, locale=locale, fuzzy_extensions=False)
        text = 'An error occurred generating a Google Cloud Images URL for: {}'
        raise Error(text.format(bucket_path))


class GoogleImage(object):

    def __init__(self, pod, bucket_path, locale=None):
        self.pod = pod
        self.locale = locale
        self.bucket_path = bucket_path
        self._base_url = None
        self._backend = None
        self._fuzzy_extensions = False
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
    def fuzzy_extensions(self):
        if self._fuzzy_extensions is None:
            for preprocessor in self.pod.list_preprocessors():
                if preprocessor.KIND == GoogleCloudImagesPreprocessor.KIND:
                    self._fuzzy_extensions = preprocessor.config.fuzzy_extensions
        return self._backend

    @property
    def backend(self):
        if self._backend is None:
            for preprocessor in self.pod.list_preprocessors():
                if preprocessor.KIND == GoogleCloudImagesPreprocessor.KIND:
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
                    message = 'Generating Google Cloud Images data -> {} ({})'
                    message = message.format(self.bucket_path, self.locale)
                else:
                    message = 'Generating Google Cloud Images data -> {}'
                    message = message.format(self.bucket_path)
                self.pod.logger.info(message)
                data = get_image_serving_data(self.backend, self.bucket_path,
                                              locale=self.locale,
                                              fuzzy_extensions=self._fuzzy_extensions)
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
    def dimensions(self):
        return '{}x{}'.format(self.width, self.height)

    @property
    def etag(self):
        return self._data['etag']

    @property
    def height(self):
        return self._data['image_metadata'].get('height')

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
    def create_google_image(ctx, bucket_path):
        if 'doc' not in ctx:
            raise Exception(
                'Missing `doc` in the template context. Are'
                ' you using `google_image` within a macro? Remember to {%'
                ' import ... with context %}.')
        doc = ctx['doc']
        pod = doc.pod
        return GoogleImage(pod, bucket_path, locale=doc.locale)



class GoogleCloudImagesPreprocessor(grow.Preprocessor):

    KIND = 'google_cloud_images'

    class Config(messages.Message):
        backend = messages.StringField(1)

    def run(self, *args, **kwargs):
        text = 'Using Google Cloud images backend -> {}'
        message = text.format(self.config.backend)
        self.pod.logger.info(message)
