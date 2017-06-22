from jinja2.ext import Extension
from protorpc import messages
import grow
import jinja2
import requests


def get_image_serving_url(backend, bucket_path):
    """Makes a request to the backend microservice capable of generating URLs
    that use Google's image-serving infrastructure."""
    params = {'gs_path': bucket_path}
    resp = requests.get(backend, params)
    return resp.json()['url']


class GoogleImage(object):

    def __init__(self, pod, bucket_path):
        self.pod = pod
        self.bucket_path = bucket_path
        self._base_url = None
        self._backend = None
        self._cache = None

    @property
    def cache(self):
        if self._cache is None:
            self._cache = self.pod.podcache.get_object_cache('ext-google-cloud-images')
        return self._cache

    @property
    def backend(self):
        if self._backend is None:
            for preprocessor in self.pod.list_preprocessors():
                if isinstance(preprocessor, GoogleCloudImagesPreprocessor):
                    self._backend = preprocessor.config.backend
        return self._backend

    @property
    def base_url(self):
        """Returns a URL corresponding to the image served by Google's
        image-serving infrastructure."""
        if self._base_url is None:
            key = '{}:{}'.format(self.backend, self.bucket_path)
            base_url = self.cache.get(key)
            if base_url is not None:
                self._base_url = base_url
            else:
                message = 'Generating serving URL -> {}'
                self.pod.logger.info(message.format(self.bucket_path))
                self._base_url = get_image_serving_url(self.backend, self.bucket_path)
                self.cache.add(key, self._base_url)
        return self._base_url

    def url(self, options=None):
        if not options:
            return self.base_url
        url = self.base_url
        return '{}={}'.format(self.base_url, '-'.join(options))



class GoogleCloudImagesExtension(Extension):

    def __init__(self, environment):
        super(GoogleCloudImagesExtension, self).__init__(environment)
        environment.globals['google_image'] = GoogleCloudImagesExtension.create_google_image

    @staticmethod
    @jinja2.contextfunction
    def create_google_image(ctx, bucket_path):
        pod = ctx['doc'].pod
        return GoogleImage(pod, bucket_path)



class GoogleCloudImagesPreprocessor(grow.Preprocessor):

    KIND = 'google_cloud_images'

    class Config(messages.Message):
        backend = messages.StringField(1)

    def run(self, *args, **kwargs):
        message = 'Using Google Cloud images backend -> {}'.format(self.config.backend)
        self.pod.logger.info(message)
