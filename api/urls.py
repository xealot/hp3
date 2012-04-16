from urllib import urlencode
from api.work.responses import NotAllowed
from django.conf.urls import patterns, include, url

from work.talker import Endpoint, API
from work.middleware import critical_middleware

class T1(Endpoint):
    #Not Implemented Test
    pass

class T2(Endpoint):
    #Echo Test
    def detail_get(self, request, id, *args, **kwargs):
        """Fetch the particular object"""
        return id

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
        return urlencode(request.GET)

    def list_post(self, request, *args, **kwargs):
        return request.data

    def list_put(self, request, *args, **kwargs):
        return request.data


urlpatterns = patterns('',
    url(r't1', include(T1(critical_middleware).urls)),
    url(r't2', include(T2(critical_middleware).urls)),
)