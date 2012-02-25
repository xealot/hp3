from django.conf import settings
from django.conf.urls import url
from django.core.exceptions import ValidationError
from pymongo import Connection
from tastypie import resources, fields
from tastypie.authorization import Authorization
from tastypie.bundle import Bundle
from tastypie.utils.urls import trailing_slash
from tastypie.validation import Validation
from tastypie.resources import ModelDeclarativeMetaclass


class ModeledValidator(Validation):
    def is_valid(self, bundle, request=None):
        try:
            bundle.data = bundle.obj.validate(bundle.data)
        except ValidationError as e:
            return e.message_dict
        return {}


class ModeledResource(resources.Resource):
    __metaclass__ = ModelDeclarativeMetaclass

    def _db(self):
        connection = Connection(**settings.MONGO_CONNECTION_PARAMS)
        return connection[settings.MONGO_DATABASE]

    def _collection(self):
        return self._db()[self._meta.resource_name]

    def _lookup_field(self):
        return getattr(self._meta, 'link_field', '_id')

    @classmethod
    def api_field_from_datamodel(cls, f, default=fields.CharField):
        """
        Returns the field type that would likely be associated with each
        Django type.
        """
        n = f.__class__.__name__
        #result = default

        if n in ('DateData', 'DateTimeData', 'TimeData'):
            result = fields.DateTimeField
        elif n in ('CharData', 'SlugData'):
            result = fields.CharField
        elif n in ('BooleanData',):
            result = fields.BooleanField
        elif n in ('FloatData',):
            result = fields.FloatField
        elif n in ('DecimalData',):
            result = fields.DecimalField
        elif n in ('IntegerData',):
            result = fields.IntegerField
        #elif n in ('FileField', 'ImageField'):
        #    result = fields.FileField
        elif n in ('ListData',):
            result = fields.ListField
        elif n in ('DictData',):
            result = fields.DictField
        else:
            raise NotImplementedError('Field has no mapping: %s' % n)
        return result

    @classmethod
    def get_fields(cls, fields=None, excludes=None):
        final_fields = {}
        fields = fields or []
        excludes = excludes or []

        if not cls._meta.object_class:
            return final_fields

        for attr, f in cls._meta.object_class.base_fields.items():
            # If the field name is already present, skip
            if f.name is None:
                f.name = attr

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

            api_field_class = cls.api_field_from_datamodel(f)
            kwargs = {
                'attribute': f.name,
                'help_text': f.help_text,
                'default': f.default.__name__ if callable(f.default) else f.default,
                'unique': True if f.unique else False,
                'readonly': True if f.readonly else False
            }

            if f.default is not None or f.readonly is True:
                kwargs['blank'] = True

            final_fields[f.name] = api_field_class(**kwargs)
            final_fields[f.name].instance_name = f.name
        return final_fields


    def get_resource_uri(self, bundle_or_obj):
        kwargs = {
            'resource_name': self._meta.resource_name,
            }

        fname = self._lookup_field()
        obj = bundle_or_obj
        if isinstance(bundle_or_obj, Bundle):
            obj = bundle_or_obj.obj

        if fname in obj:
            kwargs[fname] = obj[fname]

        if self._meta.api_name is not None:
            kwargs['api_name'] = self._meta.api_name

        return self._build_reverse_url("api_dispatch_detail", kwargs=kwargs)

    def override_urls(self):
        return [
            #This is required since /schema can't be differentiated from the detail view.
            url(r"^(?P<resource_name>%s)/schema%s$" % (self._meta.resource_name, trailing_slash()), self.wrap_view('get_schema'), name="api_get_schema"),
            #This will take into account the link_field attribute.
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)%s$" % (self._meta.resource_name, self._lookup_field(), trailing_slash()), self.wrap_view('dispatch_detail'), name="api_dispatch_detail"),
            ]

    def get_object_list(self, request):
        pass
        #return self._collection().find()

    def obj_get_list(self, request=None, **kwargs):
        # Filtering disabled for brevity...
        return self._collection().find(kwargs)

    def obj_get(self, request=None, **kwargs):
        return self._collection().find_one(kwargs)

    def obj_create(self, bundle, request=None, **kwargs):
        print bundle
        bundle.obj = RiakObject(initial=kwargs)
        bundle = self.full_hydrate(bundle)
        bucket = self._bucket()
        new_message = bucket.new(bundle.obj.uuid, data=bundle.obj.to_dict())
        new_message.store()
        return bundle

    def obj_update(self, bundle, request=None, **kwargs):
        return self.obj_create(bundle, request, **kwargs)

    def obj_delete_list(self, request=None, **kwargs):
        self._collection().remove(kwargs)

    def obj_delete(self, request=None, **kwargs):
        obj = self.obj_get(request=request, **kwargs)
        self._collection().remove({'_id': obj['_id']})

    def rollback(self, bundles):
        pass