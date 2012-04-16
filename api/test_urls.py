from api.data import DataModel, IntegerData
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

    def detail_post(self, request, id, *args, **kwargs):
        if hasattr(request.data, 'dict'):
            data = request.data.dict()
        else:
            data = request.data
        data.update(id=id)
        return data

    def detail_put(self, request, id, *args, **kwargs):
        if hasattr(request.data, 'dict'):
            data = request.data.dict()
        else:
            data = request.data
        data.update(id=id)
        return data

    def detail_patch(self, request, id, *args, **kwargs):
        if hasattr(request.data, 'dict'):
            data = request.data.dict()
        else:
            data = request.data
        data.update(id=id)
        return data


    def list_get(self, request, *args, **kwargs):
        return {'hello': True}

    def list_post(self, request, *args, **kwargs):
        return request.data

    def list_put(self, request, *args, **kwargs):
        return request.data


class T3Test1(DataModel):
    id = IntegerData()

from data import validate

class T3(Endpoint):
    @validate(T3Test1)
    def list_get(self, request):
        """Docstring"""
        pass

urlpatterns = patterns('',
    url(r't1', include(T1(critical_middleware).urls)),
    url(r't2', include(T2(critical_middleware).urls)),
    url(r't3', include(T3(critical_middleware).urls)),
)