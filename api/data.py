import datetime
import copy
import re
from django.core import validators
from django.core.exceptions import ValidationError
from django.forms.util import to_current_timezone, from_current_timezone
from django.utils import formats
from django.utils.datastructures import SortedDict
from django.utils.encoding import smart_unicode, force_unicode
from django.utils.translation import ugettext_lazy as _
from django.core.validators import BaseValidator


class NotSpecified(object): pass


class TypeValidator(BaseValidator):
    compare = lambda self, a, b: not isinstance(a, b)
    message = _(u'Ensure this value is of the currect type.')
    code = 'invalid'


def validate_required(value):
    if value in validators.EMPTY_VALUES:
        raise ValidationError(_(u'This field is required.'), code='required')


class Data(object):
    default_error_messages = {
        'invalid': _(u'Enter a valid value.'),
    }
    default_validators = [] # Default set of validators
    creation_counter = 0

    def __init__(self, name=None, default=None, verbose=None, readonly=False, unique=False, required=True, help_text=None, validators=None, error_messages=None, **kwargs):
        validators = validators or []
        self.name = name
        self.readonly = readonly
        self.default = default
        self.unique = unique #Just a flag, cannot enforce this.
        self.verbose = verbose
        self.required = required
        self.help_text = help_text
        self.error_messages = error_messages or {}

        # Increase the creation counter, and save our local copy.
        self.creation_counter = Data.creation_counter
        Data.creation_counter += 1

        #Error on impossible combinations
        if self.required and self.readonly:
            self.required = False

        #Validate the field flags.
        if self.required:
            validators.append(validate_required)

        self.validators = self.default_validators + validators

    def clean(self, value, data):
        #:TODO: You're having trouble reconciling NotSpecified with the clean and validation methods. Some fields clean everything completely, but it's hard to know when something hasn't been specified. Consider adding another structure or making data available everywhere.
        self.orig_value = value
        if value is NotSpecified and self.default is not None:
            value = self.default
            if callable(self.default):
                value = self.default()
        return value

    def validate(self, value):
        errors = []

        #WOuld love to do this in a validator but we need the original value here.
        if self.readonly:
            if self.orig_value is not NotSpecified:
                errors.append(_(u'This field is readonly.'))

        for v in self.validators:
            try:
                v(value)
            except ValidationError as e:
                if hasattr(e, 'code') and e.code in self.error_messages:
                    message = self.error_messages[e.code]
                    if e.params:
                        message = message % e.params
                    errors.append(message)
                else:
                    errors.extend(e.messages)
        if errors:
            raise ValidationError(errors)


class CharData(Data):
    default_error_messages = {
        'min_length': _(u'Ensure this value has at least %(limit_value)d characters (it has %(show_value)d).'),
        'max_length': _(u'Ensure this value has at most %(limit_value)d characters (it has %(show_value)d).'),
    }
    def __init__(self, max_length=None, min_length=None, *args, **kwargs):
        self.max_length, self.min_length = max_length, min_length
        super(CharData, self).__init__(*args, **kwargs)

        if min_length is not None:
            self.validators.append(validators.MinLengthValidator(min_length))
        if max_length is not None:
            self.validators.append(validators.MaxLengthValidator(max_length))

    def clean(self, value, data):
        value = super(CharData, self).clean(value, data)
        if value in validators.EMPTY_VALUES:
            return u''
        return smart_unicode(value)

class IntegerData(Data):
    default_error_messages = {
        'invalid': _(u'Enter a whole number.'),
        'max_value': _(u'Ensure this value is less than or equal to %(limit_value)s.'),
        'min_value': _(u'Ensure this value is greater than or equal to %(limit_value)s.'),
    }
    def __init__(self, max_value=None, min_value=None, *args, **kwargs):
        self.max_value, self.min_value = max_value, min_value
        super(IntegerData, self).__init__(*args, **kwargs)

        if max_value is not None:
            self.validators.append(validators.MaxValueValidator(max_value))
        if min_value is not None:
            self.validators.append(validators.MinValueValidator(min_value))

    def clean(self, value, data):
        value = super(IntegerData, self).clean(value, data)
        try:
            value = int(str(value))
        except (ValueError, TypeError):
            raise ValidationError(self.error_messages['invalid'])
        return value

class FloatData(IntegerData):
    default_error_messages = {
        'invalid': _(u'Enter a number.'),
    }

    def clean(self, value, data):
        value = super(FloatData, self).clean(value, data)

        if value in validators.EMPTY_VALUES:
            return None

        try:
            value = float(value)
        except (ValueError, TypeError):
            raise ValidationError(self.error_messages['invalid'])
        return value

class SlugData(CharData):
    default_error_messages = {
        'invalid': _(u"Enter a valid 'slug' consisting of letters, numbers,"
                     u" underscores or hyphens."),
        }
    default_validators = [validators.validate_slug]

    def __init__(self, default_from=None, **kwargs):
        self.default_from = default_from
        super(SlugData, self).__init__(**kwargs)

    def clean(self, value, data):
        value = super(SlugData, self).clean(value, data)
        print type(value), NotSpecified, type(value) == NotSpecified
        if value is NotSpecified and self.default_from:
            value = self.slugify(data[self.default_from])
        return value

    def slugify(self, value):
        return unicode(
            re.sub('[^\w\s-]', '', value).strip().lower().replace(" ", "-")
        )

class ListData(Data):
    default_error_messages = {
        'invalid': _(u"You must enter a valid list."),
        'min_length': _(u"The list must have at least %(limit_value)s item(s)."),
        }
    default_validators = [TypeValidator(list)]

class DictData(Data):
    default_validators = [TypeValidator(dict)]

class BaseTemporalData(Data):
    def __init__(self, input_formats=None, *args, **kwargs):
        super(BaseTemporalData, self).__init__(*args, **kwargs)
        if input_formats is not None:
            self.input_formats = input_formats

    def strptime(self, value, format):
        raise NotImplementedError()

    def clean(self, value, data):
        # Try to coerce the value to unicode.
        unicode_value = force_unicode(value, strings_only=True)
        if isinstance(unicode_value, unicode):
            value = unicode_value.strip()
            # If unicode, try to strptime against each input format.
        if isinstance(value, unicode):
            for format in self.input_formats:
                try:
                    return self.strptime(value, format)
                except ValueError:
                    if format.endswith('.%f'):
                        # Compatibility with datetime in pythons < 2.6.
                        # See: http://docs.python.org/library/datetime.html#strftime-and-strptime-behavior
                        if value.count('.') != format.count('.'):
                            continue
                        try:
                            datetime_str, usecs_str = value.rsplit('.', 1)
                            usecs = int(usecs_str[:6].ljust(6, '0'))
                            dt = datetime.datetime.strptime(datetime_str, format[:-3])
                            return dt.replace(microsecond=usecs)
                        except ValueError:
                            continue
        raise ValidationError(self.error_messages['invalid'])

class DateData(BaseTemporalData):
    input_formats = formats.get_format_lazy('DATE_INPUT_FORMATS')
    default_error_messages = {
        'invalid': _(u'Enter a valid date.'),
        }

    def clean(self, value, data):
        """
        Validates that the input can be converted to a date. Returns a Python
        datetime.date object.
        """
        if value in validators.EMPTY_VALUES:
            return None
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        return super(DateData, self).clean(value, data)

    def strptime(self, value, format):
        return datetime.datetime.strptime(value, format).date()

class TimeData(BaseTemporalData):
    input_formats = formats.get_format_lazy('TIME_INPUT_FORMATS')
    default_error_messages = {
        'invalid': _(u'Enter a valid time.')
    }

    def clean(self, value, data):
        """
        Validates that the input can be converted to a time. Returns a Python
        datetime.time object.
        """
        if value in validators.EMPTY_VALUES:
            return None
        if isinstance(value, datetime.time):
            return value
        return super(TimeData, self).clean(value, data)

    def strptime(self, value, format):
        return datetime.datetime.strptime(value, format).time()

class DateTimeData(BaseTemporalData):
    input_formats = formats.get_format_lazy('DATETIME_INPUT_FORMATS')
    default_error_messages = {
        'invalid': _(u'Enter a valid date/time.'),
    }

#    def prepare_value(self, value):
#        if isinstance(value, datetime.datetime):
#            value = to_current_timezone(value)
#        return value

    def clean(self, value, data):
        """
        Validates that the input can be converted to a datetime. Returns a
        Python datetime.datetime object.
        """
        if value in validators.EMPTY_VALUES:
            return None
        if isinstance(value, datetime.datetime):
            return from_current_timezone(value)
        if isinstance(value, datetime.date):
            result = datetime.datetime(value.year, value.month, value.day)
            return from_current_timezone(result)
        if isinstance(value, list):
            # Input comes from a SplitDateTimeWidget, for example. So, it's two
            # components: date and time.
            if len(value) != 2:
                raise ValidationError(self.error_messages['invalid'])
            if value[0] in validators.EMPTY_VALUES and value[1] in validators.EMPTY_VALUES:
                return None
            value = '%s %s' % tuple(value)
        result = super(DateTimeData, self).clean(value, data)
        return from_current_timezone(result)

    def strptime(self, value, format):
        return datetime.datetime.strptime(value, format)

class EmailData(CharData):
    default_error_messages = {
        'invalid': _(u'Enter a valid e-mail address.'),
    }
    default_validators = [validators.validate_email]

    def clean(self, value, data):
        return super(EmailData, self).clean(value, data).strip()

class BooleanData(Data):
    def clean(self, value, data):
        value = super(BooleanData, self).clean(value, data)
        if isinstance(value, basestring) and value.lower() in ('false', '0'):
            value = False
        value = bool(value)
        return value


class DeclarativeDataMetaclass(type):
    """
    Metaclass that converts Field attributes to a dictionary called
    'base_fields', taking into account parent class 'base_fields' as well.
    """
    def __new__(cls, name, bases, attrs):
        fields = [(field_name, attrs.pop(field_name)) for field_name, obj in attrs.items() if isinstance(obj, Data)]
        fields.sort(key=lambda x: x[1].creation_counter)

        for base in bases[::-1]:
            if hasattr(base, 'base_fields'):
                fields = base.base_fields.items() + fields

        attrs['base_fields'] = SortedDict(fields)
        new_class = super(DeclarativeDataMetaclass,
            cls).__new__(cls, name, bases, attrs)
        return new_class

class BaseDataModel(object):
    def validate(self, data):
        #If there are name overrides this will fail.
        cleaned_data = {}
        errors = {}
        for attr, f in self.base_fields.items():
            try:
                cleaned_data[attr] = f.clean(data.get(attr, NotSpecified), data)
                f.validate(cleaned_data[attr])
            except ValidationError as e:
                errors[attr] = e.messages
        if errors:
            raise ValidationError(errors)
        return cleaned_data

class DataModel(BaseDataModel):
    __metaclass__ = DeclarativeDataMetaclass
