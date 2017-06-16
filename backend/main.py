from google.appengine.api import app_identity
from google.appengine.api import images
from google.appengine.ext import blobstore
import json
import webapp2


class GetServingUrlHandler(webapp2.RequestHandler):

    def get(self):
        gs_path = self.request.get('gs_path')
        if not gs_path:
            self.abort(400)
            return
        gs_path = '/gs/{}'.format(gs_path.lstrip('/'))
	blob_key = blobstore.create_gs_key(gs_path)
        try:
            url = images.get_serving_url(blob_key, secure_url=True)
        except images.TransformationError:
            service_account_email = \
                '{}@appspot.gserviceaccount.com'.format(app_identity.get_application_id())
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
	('/.*', GetServingUrlHandler),
])
