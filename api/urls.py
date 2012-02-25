from django.conf.urls import patterns, include, url
from tastypie.api import Api
from tastypie.authorization import Authorization

from resources import ModeledResource, ModeledValidator
from data import *

class SystemModel(DataModel):
    name = CharData(max_length=50, min_length=2)
    slug = SlugData(default_from='name', readonly=True)
    domains = ListData(min_length=1)
    priority = IntegerData(default=10)
    enabled = BooleanData(default=True)

class SystemResource(ModeledResource):
    #:TODO: Security around removing system entries.

    class Meta:
        resource_name = 'system'
        link_field = 'slug'
        object_class = SystemModel
        authorization = Authorization()
        validation = ModeledValidator()


v1_api = Api(api_name='v1')
#v1_api.register(UserResource())
v1_api.register(SystemResource())

urlpatterns = patterns('',
    url(r'', include(v1_api.urls)),
)