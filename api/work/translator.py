"""
If it wasn't obvious, this module is responsible for converting Python types into plain
representations to go over the wire. Most notably, JSON.
"""
import time
import inspect, decimal, types
from datetime import date, datetime, time as timeobj, tzinfo, timedelta
from calendar import timegm
from json import JSONDecoder, JSONEncoder
from django.conf import settings

__author__ = 'trey'

API_DATETIME_FORMATTING = getattr(settings, 'API_DATETIME_FORMATTING', 'iso-8601')


ZERO = timedelta(0)
HOUR = timedelta(hours=1)

HIGH_PRIORITY = True
LOW_PRIORITY = False

class UTC(tzinfo):
    """UTC"""
    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return ZERO


class LocalTimezone(tzinfo):
    """Proxy timezone information from time module. (Django implementation, sans dependencies)"""
    def __init__(self, dt):
        tzinfo.__init__(self)
        self._tzname = self.tzname(dt)

    def __repr__(self):
        return self._tzname

    def utcoffset(self, dt):
        if self._isdst(dt):
            return timedelta(seconds=-time.altzone)
        else:
            return timedelta(seconds=-time.timezone)

    def dst(self, dt):
        if self._isdst(dt):
            return timedelta(seconds=-time.altzone) - timedelta(seconds=-time.timezone)
        else:
            return timedelta(0)

    def tzname(self, dt):
        return time.tzname[self._isdst(dt)]

    def _isdst(self, dt):
        tt = (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.weekday(), 0, -1)
        try:
            stamp = time.mktime(tt)
        except (OverflowError, ValueError):
            # 32 bit systems can't handle dates after Jan 2038, and certain
            # systems can't handle dates before ~1901-12-01:
            #
            # >>> time.mktime((1900, 1, 13, 0, 0, 0, 0, 0, 0))
            # OverflowError: mktime argument out of range
            # >>> time.mktime((1850, 1, 13, 0, 0, 0, 0, 0, 0))
            # ValueError: year out of range
            #
            # In this case, we fake the date, because we only care about the
            # DST flag.
            tt = (2037,) + tt[1:]
            stamp = time.mktime(tt)
        tt = time.localtime(stamp)
        return tt.tm_isdst > 0


def decoder(obj):
    if '__complex__' in obj:
        return datetime.datetime.fromtimestamp(obj['epoch'], UTC())
    return obj

def encoder(obj):
    """
    The primary role of this function is to convert datetime instances
    into a JSON representation of a UTC datetime.
    """
    if type(obj) is date:
        #Convert to datetime
        obj = datetime.combine(obj, timeobj())
    if type(obj) is datetime:
        #If object is naive, replace the lack of a timezone with the locally derived timezone.
        if obj.tzinfo is None or obj.tzinfo.utcoffset(obj) is None:
            obj = obj.replace(tzinfo=LocalTimezone(obj))
        utc_obj = obj.astimezone(UTC())
        return {'__complex__': 'datetime',
                'tz': 'UTC',
                'epoch': timegm(utc_obj.timetuple()),
                'iso8601': utc_obj.isoformat(' '),
                'rfc2822': time.strftime("%a, %d %b %Y %H:%M:%S +0000", utc_obj.timetuple())}
    raise TypeError(repr(obj) + " is not JSON serializable")

date_aware_json_decoder = JSONDecoder(encoding='utf-8', object_hook=decoder)
date_aware_json_encoder = JSONEncoder(encoding='utf-8', default=encoder, sort_keys=True,  indent=2)


class NoTransformer(Exception):
    pass


class SimpleTranslator(object):
    """
    This translator turns all objects into the most basic
    representation we know how.
    """
    def __init__(self, callback=None):
        self.tests = []
        self.callback = callback

        self.add_defaults()

    def add_defaults(self):
        """
        Load up default handled types.
        Would love to do this based on ABCs but not sure the side effects yet or if it's possible.
        """
        self.register_type('prim', (bool, long, types.NoneType, basestring, int, float),
            None) #We add these anyway to short circuit the other checks, even though they are already primitive.
        self.register_type('date', (datetime, date),
            None) #This is safe because of the JSON serializer we use.
        self.register_type('map', dict,
            lambda x: dict([ (k, self.resolve(v)) for k, v in x.iteritems() ]))
        self.register_type('list', (tuple, list, types.GeneratorType),
            lambda x: [ self.resolve(v) for v in x ])
        self.register_type('emit', lambda x: hasattr(x, '__emittable__'),
            lambda f: f.__emittable__())
        self.register_type('dec', decimal.Decimal,
            lambda x: str(x))
        self.register_type('func', (types.FunctionType, types.LambdaType),
            lambda x: x())

    def register_type(self, name, test, conv, priority=LOW_PRIORITY):
        atom = (name, test if inspect.isfunction(test) else lambda x: isinstance(x, test), conv)
        if priority:
            self.tests.insert(0, atom)
        else:
            self.tests.append(atom)

    def unregister_type(self, name):
        index = None
        for i in len(self.tests):
            if self.tests[i][0] == name:
                index = i
                break
        if index is not None:
            self.tests.pop(index)

    def get_transformer(self, obj):
        for name, test, converter in self.tests:
            if test(obj) is True:
                return converter
        raise NoTransformer('No transformer could be found for %s' % str(type(obj)))

    def resolve(self, obj):
        trans = self.get_transformer(obj)
        if trans is not None:
            return trans(obj)
        return obj

translator = SimpleTranslator()

