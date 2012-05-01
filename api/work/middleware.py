from django.core.exceptions import ValidationError
import mimeparse
from django.utils.cache import patch_cache_control
from django.utils.translation import gettext as _
from translator import translator, date_aware_json_decoder, date_aware_json_encoder

from responses import APIException

__author__ = 'trey'

#class AuthorizationMiddleware(object):
#    def process_request(self, request):
#        pass
#
#    def process_data(self, request, data_func, *args, **kwargs):
#        pass
#
#    def process_response(self, request, response):
#        pass
#
#    def process_exception(self, request, exception):
#        pass

class RequestVERBHelperMiddleware(object):
    """
    Django doesn't really process anything that isn't a POST. This middleware will make available
    the data from a PUT and a PATCH method.
    """
    verbs = ['PUT', 'PATCH']

    def process_request(self, request):
        verb = request.method.upper()
        if verb in self.verbs:
            self.convert_post_to_VERB(request, verb)

    # Based off of ``piston.utils.coerce_put_post``. Similarly BSD-licensed.
    def convert_post_to_VERB(self, request, verb):
        """
        Force Django to process the VERB.
        """
        if hasattr(request, '_post'):
            del request._post
            del request._files

        try:
            request.method = "POST"
            request._load_post_and_files()
            request.method = verb
        except AttributeError:
            request.META['REQUEST_METHOD'] = 'POST'
            request._load_post_and_files()
            request.META['REQUEST_METHOD'] = verb

        setattr(request, verb, request.POST)
        return request


class ContentSerializationMiddleware(object):
    input_types = {
        'application/json': 'json'
    }
    output_types = {
        'application/json': 'json',
        'text/javascript': 'jsonp',
    }

    def process_request(self, request):
        if not len(request.body): #If there is no payload, then don't process it.
            request.data = {}
            return None

        declared_type = request.META.get('CONTENT_TYPE', 'application/json').split(';')[0]

        if declared_type not in self.input_types:
            raise Exception(_(u'The type %s is not supported.' % declared_type))

        #Requires some deserialization.
        format = self.determine_format(request)

        request.data = getattr(self, "from_%s" % format)(request.body)
        print request.data

    def process_response(self, request, response):
        """
        If "payload" is present in the HTTPResponse then we need to serialize it to the requested type.
        """
        if hasattr(response, 'payload'):
            payload = response.payload
            options = request.GET.dict()
            format = self.determine_format(request)

            if format == 'jsonp' and 'callback' not in options:
                response = APIException(_(u"You cannot request a JSONP output without specifying a callback parameter."))()
                format = 'json'

            #Now, translate values according to specified translator and serialize.
            payload = self.translator.resolve(payload)
            response.content = getattr(self, "to_%s" % format)(payload, options)

        return response

    #def process_exception(self, request, exception):
    #    pass

    def __init__(self, translator=translator):
        self.formats = set(self.output_types.values())
        self.types = self.output_types.keys()
        self.translator = translator() if callable(translator) else translator

    def get_json_encoder(self):
        return date_aware_json_encoder

    def get_json_decoder(self):
        return date_aware_json_decoder

    def determine_format(self, request, default_format='json'):
        # First, check if they forced the format.
        if request.GET.get('format', None) in self.formats:
            return request.GET.get('format')

        # Try to use the Accepts header.
        if request.META.get('HTTP_ACCEPT', '*/*') != '*/*':
            try:
                best_format = mimeparse.best_match(reversed(self.types), request.META['HTTP_ACCEPT'])
                if best_format:
                    return self.output_types[best_format]
            except ValueError as e:
                #Invalid ACCEPT header.
                pass

        # If callback parameter is present, use JSONP.
        if 'callback' in request.GET and 'jsonp' in self.formats:
            return 'jsonp'

        return default_format

    def to_json(self, payload, options=None):
        #return json.dumps(payload, sort_keys=True)
        return self.get_json_encoder().encode(payload)

    def from_json(self, payload, options=None):
        #return json.loads(payload)
        return self.get_json_decoder().decode(payload)

    def to_jsonp(self, data, options=None):
        """
        Given some Python data, produces JSON output wrapped in the provided
        callback.
        """
        options = options or {}
        return '%s(%s)' % (options['callback'], self.to_json(data, options))


class ContractMiddleware(object):
    """
    If the view method has a contract attached to it, use it to validate input.
    """
    def process_view(self, request, view, kwargs):
        print view
        if hasattr(view, 'contract'):
            print 'SHOULD VALIDATE', view.contract
            try:
                print request.data
                data = view.contract().validate(request.data)
                print data
            except ValidationError as e:
                print e
        return None


class IEAjaxCachefixMiddleware(object):
    def process_response(self, request, response):
        if request.is_ajax():
            # IE excessively caches XMLHttpRequests, so we're disabling
            # the browser cache here.
            # See http://www.enhanceie.com/ie/bugs.asp for details.
            patch_cache_control(response, no_cache=True)
        return response


critical_middleware = (
    'api.work.middleware.RequestVERBHelperMiddleware',
    'api.work.middleware.ContentSerializationMiddleware',
    'api.work.middleware.ContractMiddleware',
    'api.work.middleware.IEAjaxCachefixMiddleware'
)













