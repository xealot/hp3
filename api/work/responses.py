"""
Exceptions should know how to represent their own data and types. For intance, a bad request exception should
understand what data to return to the talker so that the user can comprehend the message.
"""
from datetime import datetime
from django.conf import settings
from django.http import HttpResponse
from django.utils.translation import gettext as _

__author__ = 'trey'

def create_response(payload, status, headers):
    response = HttpResponse('', status=status)
    response.payload = payload
    for k,v in headers.items():
        response[k] = v
    return response

class APIResponse(object):
    status = 200
    def __init__(self, payload='', headers=None):
        self.payload = payload
        self.headers = headers or {}

    def __call__(self):
        return create_response(self.payload, self.status, self.headers)

class APIException(Exception):
    status = 500
    message = _(u'This request could not be completed.')

    def __init__(self, message=None, payload='', headers=None):
        super(APIException, self).__init__()
        self.payload = payload
        self.headers = headers or {}
        if message is not None:
            self.message = message

    def create_payload(self):
        data = dict(
            status=self.status,
            message=self.message,
            timestamp=datetime.now(),
            details=self.payload
        )

        if settings.DEBUG:
            import traceback
            import sys
            the_trace = traceback.extract_tb(sys.exc_info()[2])

            data.update(
                error_message=unicode(self.message),
                traceback=the_trace,
            )
        return data

    def __call__(self):
        return create_response(self.create_payload(), self.status, self.headers)


class APIOK(APIResponse): pass

class APICreated(APIResponse):
    status = 201 #Created

    def __init__(self, *args, **kwargs):
        location = kwargs.pop('location', None)

        super(APICreated, self).__init__(*args, **kwargs)
        if location is not None:
            self.headers.update(Location=location)

class APINoContent(APIResponse):
    status = 204 #No Content

class PlainException(APIException):
    def __init__(self, exception, headers=None):
        super(PlainException, self).__init__(message=str(exception), headers=headers)
        self.exception = exception

    def create_payload(self):
        data = super(PlainException, self).create_payload()
        data.update(type=self.exception.__class__.__name__)
        return data



class HttpNotImplemented(APIException):
    status = 501
    message = _(u'This HTTP method is not implemented')

class BadRequest(APIException):
    status = 400
    message = _(u'Bad Request')

class NotAllowed(APIException):
    #:TODO: must have allow header.
    status = 405
    message = _(u'This method is not allowed here.')

    def __init__(self, permitted_methods):
        super(NotAllowed, self).__init__()
        self.headers['Allow'] = ', '.join(permitted_methods)