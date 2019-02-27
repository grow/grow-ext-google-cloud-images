from datetime import datetime, timedelta

HTTP_DATE_FMT_GMT = "%a, %d %b %Y %H:%M:%S GMT"
HTTP_DATE_FMT_UTC = "%a, %d %b %Y %H:%M:%S UTC"


class expires(object):

    def __init__(self, expire_interval=None, force_expires=None, edge=True, type="webapp2"):

        assert expire_interval is None or isinstance(expire_interval, timedelta)
        assert force_expires is None or isinstance(force_expires, datetime)
        assert type in ('webapp2', 'django')

        self.force_expires = force_expires
        self.expire_interval = expire_interval
        self.edge = edge
        self.type = type

    def __call__(self, handler_method):
        return getattr(self, self.type)(handler_method)

    def _set_response_headers(self, response_headers):
        if response_headers.get('no-cache'):
            return

        if self.force_expires:
            expires = self.force_expires
            self.expire_interval = expires - datetime.utcnow()
        else:
            expires = datetime.utcnow() + self.expire_interval

        if self.expire_interval.days > 364:
            max_age = 364 * 24 * 60 * 60
        else:
            max_age = self.expire_interval.total_seconds()

        response_headers['Expires'] = expires.strftime(HTTP_DATE_FMT_GMT)

        if self.edge:
            response_headers['Cache-Control'] = 'public, max-age=%d' % max_age
            response_headers['Pragma'] = 'Public'


    def webapp2(self, handler_method):
        if not self.expire_interval and not self.force_expires:
            return handler_method

        def wrapper(h, *args, **kwargs):
            result = handler_method(h, *args, **kwargs)
            self._set_response_headers(h.response.headers)
            return result

        return wrapper

    def django(self, handler_method):
        if not self.expire_interval and not self.force_expires:
            return handler_method

        def wrapper(request, *args, **kwds):
            response = handler_method(request, *args, **kwds)
            self._set_response_headers(response)

            return response

        return wrapper