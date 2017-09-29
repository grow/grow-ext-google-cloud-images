from jinja2.ext import Extension
from protorpc import messages
import grow
import jinja2
import requests


class Error(Exception):
    pass


def get_image_serving_data(backend, bucket_path, locale=None):
    """Makes a request to the backend microservice capable of generating URLs
    that use Google's image-serving infrastructure."""
    params = {'gs_path': bucket_path}
    if locale:
        params['locale'] = locale
    resp = requests.get(backend, params)
    try:
        return resp.json()
    except ValueError:
        text = 'An error occurred generating a Google Cloud Images URL for: {}'
        raise Error(text.format(bucket_path))


class GoogleImage(object):

    def __init__(self, pod, bucket_path, locale=None):
        self.pod = pod
        self.locale = locale
        self.bucket_path = bucket_path
        self._base_url = None
        self._backend = None
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
    def backend(self):
        if self._backend is None:
            for preprocessor in self.pod.list_preprocessors():
                if preprocessor.KIND == GoogleCloudImagesPreprocessor.KIND:
                    self._backend = preprocessor.config.backend
        return self._backend

    @property
    def _data(self):
        if self.__data is None:
            if self.locale:
                message = 'Generating Google Cloud Images data -> {} ({})'
                message = message.format(self.bucket_path, self.locale)
            else:
                message = 'Generating Google Cloud Images data -> {}'
                message = message.format(self.bucket_path)
            self.pod.logger.info(message)
            data = get_image_serving_data(self.backend, self.bucket_path,
                                          locale=self.locale)
            self.__data = data
        return self.__data

    @property
    def _cache_key(self):
        if '{locale}' in self.bucket_path:
            return '{}:{}:{}'.format(self.backend, self.bucket_path, self.locale)
        return '{}:{}'.format(self.backend, self.bucket_path)

    @property
    def base_url(self):
        """Returns a URL corresponding to the image served by Google's
        image-serving infrastructure."""
        if self._base_url is None:
            base_url = self.cache.get(self._cache_key)
            if base_url is not None:
                self._base_url = base_url
            else:
                self._base_url = self._data.get('url')
                self.cache.add(self._cache_key, self._base_url)
        return self._base_url

    @property
    def etag(self):
        return self._data['etag']

    def url(self, options=None):
        if not options:
            return self.base_url
        return '{}={}'.format(self.base_url, '-'.join(options))


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
