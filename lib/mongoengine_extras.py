import re
from mongoengine.base import ValidationError
from mongoengine.document import Document
from mongoengine.fields import StringField, ListField
from mongoengine.queryset import QuerySetManager

def slugify(inputstring):
    return unicode(
        re.sub('[^\w\s-]', '', inputstring).strip().lower().replace(" ", "-")
    )

class SlugField(StringField):
    """A field that validates input as a standard slug.
    """
    slug_regex = re.compile(r"^[-\w]+$")

    def _validate(self, value):
        if not self.slug_regex.match(value):
            raise ValidationError('This string is not a slug: %s' % value)


class AutoSlugField(SlugField):
    """A field that that produces a slug from the inputs and auto-
    increments the slug if the value already exists."""

    def __init__(self, populate_from=None, **kwargs):
        # This is going to be a unique field no matter what
        self.instance = None
        self.populate_from = populate_from
        super(AutoSlugField, self).__init__(**kwargs)

    def __set__(self, instance, value):
        """Descriptor for assigning a value to a field in a document.
        """
        self.instance = instance
        if value is None and self.required:
            value = '' # need to not store None so validation will proceed
        else:
            value = slugify(value)
        instance._data[self.name] = value
        return value

    def _validate(self, value):
        if not value and self.populate_from:
            value = unicode(self.instance._data[self.populate_from])
            value = self.__set__(self.instance, value)
        super(AutoSlugField, self)._validate(value)


class BetterListField(ListField):
    def validate(self, value):
        """Make sure that a list of valid fields is being used.
        """
        if not isinstance(value, (list, tuple)):
            raise ValidationError('Only lists and tuples may be used in a list field')

        item = None
        try:
            [self.field.validate(item) for item in value]
        except ValidationError, err:
            raise ValidationError('Invalid ListField item (%s) because: %s' % (str(item), str(err)))
        except Exception, err:
            print err
            raise ValidationError('Invalid ListField item (%s)' % str(item))


class Validating(object):
    def validate_all(self):
        """Ensure that all fields' values are valid and that required fields
        are present.
        """
        # Get a list of tuples of field names and their current values
        errors = {}
        fields = [(field, getattr(self, name)) for name, field in self._fields.items()]

        # Ensure that each field is matched to a valid value
        for field, value in fields:
            if value is not None:
                try:
                    field._validate(value)
                except (ValidationError, ValueError, AttributeError, AssertionError), e:
                    errors[field.name] = "Invalid value, '%s'" % value
            elif field.required:
                errors[field.name] = "Required"
        return errors
