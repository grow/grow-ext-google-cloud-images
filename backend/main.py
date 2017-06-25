from google.appengine.api import app_identity
from google.appengine.api import images
from google.appengine.ext import blobstore
import json
import os
import webapp2


class GetServingUrlHandler(webapp2.RequestHandler):

    def get(self, gs_path):
        gs_path = self.request.get('gs_path') or gs_path
        service_account_email = \
            '{}@appspot.gserviceaccount.com'.format(app_identity.get_application_id())
        if not gs_path:
            detail = (
                'Usage: Share your GCS objects with `{}` and make another'
                ' request to this service. Make requests to: '
                ' {}:{}/<bucket>/<path>.ext'.format(
                    service_account_email,
                    os.getenv('wsgi.url_scheme'),
                    os.getenv('HTTP_HOST')))
            self.abort(400, detail=detail)
            return
        gs_path = '/gs/{}'.format(gs_path.lstrip('/'))
        try:
            blob_key = blobstore.create_gs_key(gs_path)
            url = images.get_serving_url(blob_key, secure_url=True)
        except images.ObjectNotFoundError:
            detail = (
                'The object was not found. Ensure the following service'
                ' account has access to the object in Google Cloud Storage:'
                ' {}'.format(service_account_email))
            self.abort(400, explanation='ObjectNotFoundError', detail=detail)
            return
        except (images.TransformationError, ValueError):
            detail = (
                'There was a problem transforming the image. Ensure the'
                ' following service account has access to the object in Google Cloud'
                ' Storage: {}'.format(service_account_email))
            self.abort(400, explanation='TransformationError', detail=detail)
            return
        # TODO(jeremydw): This is a WIP; should be updated based on Grow's integration.
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
  ('/(.*)', GetServingUrlHandler),
])
