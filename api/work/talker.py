"""
responsible for breaking down communications, listening to verbs and passing that information to the
middleware and eventual handler.
"""
from functools import partial
from api.work.responses import PlainException
from django.conf import settings
from django.conf.urls import url, patterns, include
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.translation import gettext as _
from django.utils.importlib import import_module

from responses import APIResponse, APIOK, APIException, NotAllowed, HttpNotImplemented

__author__ = 'trey'

#Settings and Defaults
API_HANDLE_EXCEPTIONS   = getattr(settings, 'API_HANDLE_EXCEPTIONS', False)
API_ALLOW_MISSING_SLASH = getattr(settings, 'API_ALLOW_MISSING_SLASH', False)

def load_middleware(middleware):
    from django.core import exceptions
    middleware_pipeline = {
        'request': [],
        'view': [],
        'response': [],
        'exception': []
    }

    for middleware_path in middleware:
        try:
            mw_module, mw_classname = middleware_path.rsplit('.', 1)
        except ValueError:
            raise exceptions.ImproperlyConfigured('%s isn\'t a middleware module' % middleware_path)
        try:
            mod = import_module(mw_module)
        except ImportError, e:
            raise exceptions.ImproperlyConfigured('Error importing middleware %s: "%s"' % (mw_module, e))
        try:
            mw_class = getattr(mod, mw_classname)
        except AttributeError:
            raise exceptions.ImproperlyConfigured('Middleware module "%s" does not define a "%s" class' % (mw_module, mw_classname))
        try:
            mw_instance = mw_class()
        except exceptions.MiddlewareNotUsed:
            continue

        if hasattr(mw_instance, 'process_request'):
            middleware_pipeline['request'].append(mw_instance.process_request)
        if hasattr(mw_instance, 'process_view'):
            middleware_pipeline['view'].append(mw_instance.process_view)
        if hasattr(mw_instance, 'process_response'):
            middleware_pipeline['response'].insert(0, mw_instance.process_response)
        if hasattr(mw_instance, 'process_exception'):
            middleware_pipeline['exception'].insert(0, mw_instance.process_exception)

    return middleware_pipeline


class API(object):
    """
    This class provides a collection of endpoints into a single structure that can be used
    just like a regular single endpoint.
    """
    def __init__(self, endpoints=(), middleware=None):
        self.endpoints = []
        self.middleware = load_middleware(middleware or ())

        [self.add(n, e) for n, e in endpoints] #MAP() works well, PYPY works better.

    def add(self, location, endpoint):
        endpoint = endpoint() if callable(endpoint) else endpoint
        endpoint.middleware = self.middleware #Override the endpoint specific middleware with our own.
        self.endpoints.append((
            location,
            endpoint() if callable(endpoint) else endpoint,
        ))

    @property
    def urls(self):
        """
        This is responsible for unrolling all of the endpoint URLS into a single url conf with the appropriate
        prefixes.
        """
        urlpatterns = patterns('',
            *[url(r"^%s/" % location, include(endpoint.urls)) for location, endpoint in self.endpoints]
        )
        return urlpatterns


class Endpoint(object):
    """
    This class also provides callbacks to handle serialization of special objects. These methods will
    begin with serialize and end with the classname of the object to be serialized. (e.g. serialize_datetime)

    These methods can return 3 different options.
    1) An HTTPResponse object which will pass directly through to the client.
    2) An APIResponse object which will be serialized appropriately.
    3) It can raise an exception, which will be presented to the client in the correct fashion.

    """
    http_method_names = ['get', 'post', 'put', 'delete', 'options']

    parameter_mask = "\w\d-"
    params = ()
    middleware = ()

    def __init__(self, params=(), middleware=()):
        if params:
            self.params = params
        if middleware:
            self.middleware = middleware

    def install_middleware(self):
        if not hasattr(self, '_middleware'):
            self._middleware = load_middleware(self.middleware)

    def base_urls(self):
        s = '/?' if API_ALLOW_MISSING_SLASH else '/'

        pattern = ''
        if self.params:
            pattern = '/' + '/'.join(['(?P<%s>[%s]*)' % (param, self.parameter_mask) for param in self.params])

        return [
            url(r"^%s%s$" % (pattern, s), self.dispatch, name="api_dispatch"),

            #url(r"^/(?P<id>[\w\d-]*)%s$" % s, self.wrap_view(partial(self.dispatch, 'detail')), name="api_dispatch_detail"),
            #url(r"^(?P<resource_name>%s)%s$" % (self._meta.resource_name, s), self.wrap_view('dispatch_list'), name="api_dispatch_list"),
            #url(r"^(?P<resource_name>%s)/schema%s$" % (self._meta.resource_name, s), self.wrap_view('get_schema'), name="api_get_schema"),
            #url(r"^(?P<resource_name>%s)/set/(?P<pk_list>\w[\w/;-]*)/$" % self._meta.resource_name, self.wrap_view('get_multiple'), name="api_get_multiple"),
            #url(r"^(?P<resource_name>%s)/(?P<pk>\w[\w/-]*)%s$" % (self._meta.resource_name, trailing_slash()), self.wrap_view('dispatch_detail'), name="api_dispatch_detail"),
        ]

    def override_urls(self):
        return []

    @property
    def urls(self):
        return patterns('', *(self.override_urls() + self.base_urls()))

    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        self.install_middleware()

        try:
            request_method = request.method.lower()
            if request_method not in self.http_method_names:
                raise NotAllowed(self.http_method_names)

            method = getattr(self, request_method, None)
            if method is None:
                raise HttpNotImplemented(
                    _(u'The "%s" method is not implemented.' % request_method)
                )

            #Request middleware
            response = None
            for middleware_method in self._middleware['request']:
                response = middleware_method(request)
                if response:
                    break

            if response is None:
                try:
                    for middleware_method in self._middleware['view']:
                        response = middleware_method(request, method, kwargs)
                        if response:
                            break

                    if response is None:
                        response = method(request, *args, **kwargs)

                    if response is None:
                        return HttpResponse(status=201) #No Content

                except Exception as e:
                    for middleware_method in self._middleware['exception']:
                        response = middleware_method(request, e)
                        if response:
                            break
                    if response is None:
                        raise

            # Normalize response from view_func based on known response types.
            # Responses from view functions should be and HTTPResponse, APIResponse
            # or a bare response which will be wrapped in an APIResponse
            if isinstance(response, APIResponse):
                response = response()
            elif not isinstance(response, HttpResponse):
                response = APIOK(response)() #Just received a raw value...
        except APIException as e:
            response = e()
        except Exception as e:
            #if settings.DEBUG and not API_HANDLE_EXCEPTIONS:
            #    raise
            response = PlainException(e)()
            #return self._handle_500(request, e)

        try:
            for middleware_method in self._middleware['response']:
                response = middleware_method(request, response)
        except Exception as e:
            response = HttpResponse(str(e))

        return response


#    def wrap_view(self, view_func):
#        """
#        All of the WORK happens here. The flow through the serizlizer, the middlewares and the response and exception
#        handling.
#        """
#        @csrf_exempt
#        def wrapper(request, **kwargs):
#            self.install_middleware()
#
#            try:
#                #Request middleware
#                response = None
#                for middleware_method in self._middleware['request']:
#                    response = middleware_method(request)
#                    if response:
#                        break
#
#                if response is None:
#                    try:
#                        response = view_func(request, **kwargs)
#                    except Exception as e:
#                        for middleware_method in self._middleware['exception']:
#                            response = middleware_method(request, e)
#                            if response:
#                                break
#                        if response is None:
#                            raise
#
#                # Normalize response from view_func based on known response types.
#                # Responses from view functions should be and HTTPResponse, APIResponse
#                # or a bare response which will be wrapped in an APIResponse
#                if isinstance(response, APIResponse):
#                    response = response()
#                elif not isinstance(response, HttpResponse):
#                    response = APIOK(response)() #Just received a raw value...
#            except APIException as e:
#                response = e()
#            except Exception as e:
#                #if settings.DEBUG and not API_HANDLE_EXCEPTIONS:
#                #    raise
#                response = PlainException(e)()
#                #return self._handle_500(request, e)
#
#            try:
#                for middleware_method in self._middleware['response']:
#                    response = middleware_method(request, response)
#            except Exception as e:
#                response = HttpResponse(str(e))
#
#            return response
#
#        return wrapper


class DetailEndpoint(Endpoint):
    params = ('id',)


class DataReference(object):
    def detail_get(self, request, id, *args, **kwargs):
        """Fetch the particular object"""
        raise NotAllowed()

    def detail_put(self, request, id, *args, **kwargs):
        """Create/Replace a new entity at this location"""
        raise NotAllowed()

    def detail_patch(self, request, id, *args, **kwargs):
        """Partially update a record at this location"""
        raise NotAllowed()

    def detail_delete(self, request, id, *args, **kwargs):
        """Delete an entity at this location"""
        raise NotAllowed()

    def list_get(self, request, *args, **kwargs):
        """Fetch the list of objects at this location"""
        raise NotAllowed()

    def list_post(self, request, *args, **kwargs):
        """
        Create a new entity using the enclosed data

        This method should return a 200 (OK) or 204 (No Content).

        If this request creates an entity that can be referenced by a URI 201 (Created) should be returned,
        a location header should also be supplied.
        """
        raise NotAllowed()

    def list_put(self, request, *args, **kwargs):
        """CLOBBER a whole list of items, this probably should never be implemented."""
        raise NotAllowed()
