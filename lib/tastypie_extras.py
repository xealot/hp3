from django.conf.urls.defaults import *
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned, ValidationError
from django.http import HttpResponse, Http404
import mongoengine
from tastypie.api import Api
from tastypie import fields
from tastypie.fields import ApiField, BooleanField, IntegerField, ListField, DateTimeField, CharField, DictField, RelatedField, NOT_PROVIDED
from tastypie.serializers import Serializer
from tastypie.utils.mime import determine_format, build_content_type
from tastypie.authorization import Authorization
from tastypie.bundle import Bundle
from tastypie.exceptions import NotFound, BadRequest, InvalidFilterError, HydrationError, InvalidSortError, ImmediateHttpResponse, ApiFieldError
from tastypie.http import HttpAccepted, HttpCreated
from tastypie.resources import Resource, ModelDeclarativeMetaclass
from tastypie.utils import is_valid_jsonp_callback_value, dict_strip_unicode_keys, trailing_slash


class EmbeddedDocumentField(DictField):
    """
    A dictionary field.
    """
    def convert(self, value):
        if value is None:
            return None
        d = {}
        for k in value._fields.keys():
            d[k] = getattr(value, k)
        return d


class EmptyApi(Api):
    @property
    def urls(self):
        """
        Provides URLconf details for the ``Api`` and all registered
        ``Resources`` beneath it.
        """
        pattern_list = [
            url(r"^$", self.wrap_view('top_level'), name="empty_api_%s_top_level" % self.api_name),
            ]

        for name in sorted(self._registry.keys()):
            self._registry[name].api_name = self.api_name
            pattern_list.append((r"^(?P<api_name>%s)" % self.api_name, include(self._registry[name].urls)))

        urlpatterns = self.override_urls() + patterns('',
            *pattern_list
        )
        return urlpatterns


class SiteApi(Api):
    @property
    def urls(self):
        """
        Provides URLconf details for the ``Api`` and all registered
        ``Resources`` beneath it.
        """
        pattern_list = [
            url(r"^(?P<api_name>%s)/(?P<site_id>[0-9a-zA-Z-_]+)%s$" % (self.api_name, trailing_slash()), self.wrap_view('top_level'), name="site_api_%s_top_level" % self.api_name),
            ]

        for name in sorted(self._registry.keys()):
            self._registry[name].api_name = self.api_name
            pattern_list.append((r"^(?P<api_name>%s)/" % self.api_name, include(self._registry[name].urls)))

        urlpatterns = self.override_urls() + patterns('',
            *pattern_list
        )
        return urlpatterns

    def top_level(self, request, api_name=None, **kwargs):
        """
        A view that returns a serialized list of all resources registers
        to the ``Api``. Useful for discovery.
        """
        # TODO: Limit visibility of API to valid site IDs only.
        # TODO: Potentially, we could only give pieces of the API out based on site ID.

        serializer = Serializer()
        available_resources = {}

        if api_name is None:
            api_name = self.api_name

        for name in sorted(self._registry.keys()):
            kw_bru = {
                'api_name': api_name,
                'resource_name': name,
                }
            kw_bru.update(self._registry[name].api_additional_parameters())
            kw_bru.update(kwargs)
            available_resources[name] = {
                'list_endpoint': self._build_reverse_url("api_dispatch_list", kwargs=kw_bru),
                'schema': self._build_reverse_url("api_get_schema", kwargs=kw_bru),
                }

        desired_format = determine_format(request, serializer)
        options = {}

        if 'text/javascript' in desired_format:
            callback = request.GET.get('callback', 'callback')

            if not is_valid_jsonp_callback_value(callback):
                raise BadRequest('JSONP callback name is invalid.')

            options['callback'] = callback

        serialized = serializer.serialize(available_resources, desired_format, options)
        return HttpResponse(content=serialized, content_type=build_content_type(desired_format))


class MERef(RelatedField):
    """
    Provides access to related data via foreign key.

    This subclass requires Django's ORM layer to work properly.
    """
    help_text = 'A single related resource. Can be either a URI or set of nested resource data.'

    def __init__(self, to, attribute, related_name=None, default=NOT_PROVIDED,
                 null=False, blank=False, readonly=True, full=False,
                 unique=False, help_text=None):
        super(MERef, self).__init__(
            to, attribute, related_name=related_name, default=default,
            null=null, blank=blank, readonly=readonly, full=full,
            unique=unique, help_text=help_text
        )
        self.fk_resource = None

    def dehydrate(self, bundle):
        try:
            foreign_obj = getattr(bundle.obj, self.attribute)
        except ObjectDoesNotExist:
            foreign_obj = None

        if not foreign_obj:
            if not self.null:
                raise ApiFieldError("The model '%r' has an empty attribute '%s' and doesn't allow a null value." % (bundle.obj, self.attribute))

            return None

        self.fk_resource = self.get_related_resource(foreign_obj)
        fk_bundle = Bundle(obj=foreign_obj, request=bundle.request)
        return self.dehydrate_related(fk_bundle, self.fk_resource)

    def hydrate(self, bundle):
        value = super(MERef, self).hydrate(bundle)

        if value is None:
            return value

        return self.build_related_resource(value, request=bundle.request)


class MongoEngineResource(Resource):
    __metaclass__ = ModelDeclarativeMetaclass

    class Meta:
        object_class = mongoengine.Document
        authorization = Authorization()

    @classmethod
    def api_field_from_mongoengine(cls, f, default=CharField):
        """
        Returns the field type that would likely be associated with each
        Django type.
        """
        n = f.__class__.__name__

        result = default

        if n in ('DateField', 'DateTimeField'):
            result = fields.DateTimeField
        elif n in ('BooleanField',):
            result = fields.BooleanField
        elif n in ('FloatField',):
            result = fields.FloatField
        elif n in ('DecimalField',):
            result = fields.DecimalField
        elif n in ('IntField',):
            result = fields.IntegerField
        elif n in ('FileField', 'ImageField'):
            result = fields.FileField
        elif n in ('EmbeddedDocumentField',):
            result = EmbeddedDocumentField
        elif n in ('ListField', 'BetterListField'):
            result = fields.ListField
        elif n in ('DictField',):
            result = fields.DictField
        elif n in ('ReferenceField',):
            result = MERef

        return result

    @classmethod
    def get_fields(cls, fields=None, excludes=None):
        final_fields = {}
        fields = fields or []
        excludes = excludes or []

        object_class = cls.Meta.object_class
        for attr in dir(object_class):
            f = getattr(object_class, attr, None)
            # skip non-mongo-related fields
            if not isinstance(f, mongoengine.base.BaseField):
                continue

            # If the field name is already present, skip
            if f.name in cls.base_fields:
                continue

            # If field is not present in explicit field listing, skip
            if fields and f.name not in fields:
                continue

            # If field is in exclude list, skip
            if excludes and f.name in excludes:
                continue

            if f.name is None:
                f.name = attr

            if f.name == 'id':
                f.unique = True

            api_field_class = cls.api_field_from_mongoengine(f)
            kwargs = {
                'attribute': f.name,
                'help_text': f.help_text,
                'default': f.default.__name__ if callable(f.default) else f.default,
                'unique': True if f.unique or f.unique_with else False
            }

            if not f.required and f.default is None:
                kwargs['blank'] = True

            if f.unique_with:
                kwargs['help_text'] = 'Unique when combined with %s' % f.unique_with

            if f.__class__.__name__ == 'ReferenceField':
                #continue
                kwargs.update(to='api.urls.SystemResource')

            final_fields[f.name] = api_field_class(**kwargs)
            final_fields[f.name].instance_name = f.name

        return final_fields

    def build_schema(self):
        """
        Returns a dictionary of all the fields on the resource and some
        properties about those fields.

        Used by the ``schema/`` endpoint to describe what will be available.
        """
        data = {
            'fields': {},
            'default_format': self._meta.default_format,
            'allowed_list_http_methods': self._meta.list_allowed_methods,
            'allowed_detail_http_methods': self._meta.detail_allowed_methods,
            'default_limit': self._meta.limit,
            }

        if self._meta.ordering:
            data['ordering'] = self._meta.ordering

        if self._meta.filtering:
            data['filtering'] = self._meta.filtering

        for field_name, field_object in self.fields.items():
            data['fields'][field_name] = {
                'default': field_object.default,
                'type': field_object.dehydrated_type,
                'nullable': field_object.null,
                'blank': field_object.blank,
                'readonly': field_object.readonly,
                'help_text': field_object.help_text,
                'unique': field_object.unique,
                }

        return data

    def _convert_field(self, field, value):
        attr = getattr(self._meta.object_class, field)
        if not isinstance(attr, mongoengine.DateTimeField) and field not in ['pk', 'id']:
            return value
        return None

    def build_filters(self, filters=None):
        """
        Given a dictionary of filters, create the necessary ORM-level filters.

        Keys should be resource fields, **NOT** model fields.

        Valid values are either a list of Django filter types (i.e.
        ``['startswith', 'exact', 'lte']``), the ``ALL`` constant or the
        ``ALL_WITH_RELATIONS`` constant.
        """
        # At the declarative level:
        #     filtering = {
        #         'resource_field_name': ['exact', 'startswith', 'endswith', 'contains'],
        #         'resource_field_name_2': ['exact', 'gt', 'gte', 'lt', 'lte', 'range'],
        #         'resource_field_name_3': ALL,
        #         'resource_field_name_4': ALL_WITH_RELATIONS,
        #         ...
        #     }
        # Accepts the filters as a dict. None by default, meaning no filters.
        if filters is None:
            filters = {}

        qs_filters = {}

        for field_name, value in filters.items():
            if not field_name in self.fields:
                # It's not a field we know about. Move along citizen.
                continue

            if value in ['true', 'True', True]:
                value = True
            elif value in ['false', 'False', False]:
                value = False
            elif value in ('nil', 'none', 'None', None):
                value = None

            qs_filters[field_name] = value

        return qs_filters

    def get_resource_uri(self, bundle_or_obj):
        kwargs = {
            'resource_name': self._meta.resource_name,
            'pk': bundle_or_obj.obj.pk if isinstance(bundle_or_obj, Bundle) else bundle_or_obj.pk
        }

        if self._meta.api_name is not None:
            kwargs['api_name'] = self._meta.api_name

        return self._build_reverse_url("api_dispatch_detail", kwargs=kwargs)

    def _get_object_class(self, request, filters=None):
        return self._meta.object_class

    def get_object_list(self, request):
        return self._meta.object_class.all()

    def _check_required_filters(self, request, filters):
        if hasattr(self._meta, 'required_filters'):
            for filter in self._meta.required_filters:
                if not filters.get(filter, None):
                    raise Http404("The filter '%s' is required to list resources from this source." % filter)

    def obj_get_list(self, request=None, **kwargs):
        filters = {}

        if hasattr(request, 'GET'):
            # Grab a mutable copy.
            filters = request.GET.copy()

        self._check_required_filters(request, filters)

        # Update with the provided kwargs.
        filters.update(kwargs)

        object_class = self._get_object_class(request, filters=filters)
        applicable_filters = self.build_filters(filters=filters)

        return object_class.objects.filter(**applicable_filters)

    def obj_get(self, request=None, **kwargs):
        if hasattr(request, 'GET'):
            # Grab a mutable copy.
            filters = request.GET.copy()
        object_class = self._get_object_class(request, filters=filters)
        return object_class.objects.get(**kwargs)

    def obj_create(self, bundle, request=None, **kwargs):
        self._meta.object_class = self._get_object_class(request, filters=request.GET.copy())

        for k,v in bundle.data.iteritems():
            value = self._convert_field(k, v)
            if value is not None:
                bundle.data[k] = value
        bundle.obj = self._meta.object_class.objects.create(**bundle.data)
        bundle = self.full_hydrate(bundle)
        return bundle

    def obj_update(self, bundle, request=None, **kwargs):
        self._meta.object_class = self._get_object_class(request, filters=request.GET.copy())

        updates = {}
        for k,v in bundle.data.iteritems():
            try:
                value = self._convert_field(k, v)
                if value is not None:
                    updates['set__%s' % k] = value
            except AttributeError, ae:
                pass
                #print 'ae', ae

        update_val = self._meta.object_class.objects.filter(**kwargs)
        update_val.update_one(**updates)

        bundle.obj = self._meta.object_class.objects.get(**kwargs)
        bundle = self.full_hydrate(bundle)
        return bundle

    def obj_delete_list(self, request=None, **kwargs):
        self._meta.object_class.objects.filter(**kwargs).delete()

    def obj_delete(self, request=None, **kwargs):
        self._meta.object_class.objects.get(**kwargs).delete()

    def rollback(self, bundles):
        pass

    def build_bundle_custom_class(self, obj=None, data=None, **kwargs):
        if obj is None:
            if kwargs['request']:
                obj = self._get_object_class(kwargs['request'], filters=dict(kwargs['request'].GET.items()))
        return Bundle(obj, data)

    def post_list(self, request, **kwargs):
        deserialized = self.deserialize(request, request.raw_post_data, format=request.META.get('CONTENT_TYPE', 'application/json'))
        deserialized = self.alter_deserialized_list_data(request, deserialized)
        bundle = self.build_bundle_custom_class(data=dict_strip_unicode_keys(deserialized), request=request)
        self.is_valid(bundle, request)
        updated_bundle = self.obj_create(bundle, request=request)
        return HttpCreated(location=self.get_resource_uri(updated_bundle))

    def put_detail(self, request, **kwargs):
        deserialized = self.deserialize(request, request.raw_post_data, format=request.META.get('CONTENT_TYPE', 'application/json'))
        deserialized = self.alter_deserialized_detail_data(request, deserialized)
        bundle = self.build_bundle_custom_class(data=dict_strip_unicode_keys(deserialized), request=request)
        self.is_valid(bundle, request)

        try:
            updated_bundle = self.obj_update(bundle, request=request, pk=kwargs.get('pk'))
            return HttpAccepted()
        except (NotFound, MultipleObjectsReturned):
            updated_bundle = self.obj_create(bundle, request=request, pk=kwargs.get('pk'))
            return HttpCreated(location=self.get_resource_uri(updated_bundle))