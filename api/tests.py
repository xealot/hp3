"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""
from urlparse import urlparse

from django.test import TestCase
from django.test.client import Client, MULTIPART_CONTENT, FakePayload, RequestFactory
from data import *
import json


# Patch the Client() utility to support the PATCH verb...... HAR HAR HAR
def patch(self, path, data={}, content_type=MULTIPART_CONTENT, **extra):
    post_data = self._encode_data(data, content_type)

    parsed = urlparse(path)
    r = {
        'CONTENT_LENGTH': len(post_data),
        'CONTENT_TYPE':   content_type,
        'PATH_INFO':      self._get_path(parsed),
        'QUERY_STRING':   parsed[4],
        'REQUEST_METHOD': 'PATCH',
        'wsgi.input':     FakePayload(post_data),
        }
    r.update(extra)
    return self.request(**r)
RequestFactory.patch = patch

def patch(self, path, data={}, content_type=MULTIPART_CONTENT,
         follow=False, **extra):
    """
    Requests a response from the server using PATCH.
    """
    response = super(Client, self).patch(path, data=data, content_type=content_type, **extra)
    if follow:
        response = self._handle_redirects(response, **extra)
    return response
Client.patch = patch



class FieldBehaviorTestModel(DataModel):
    nn = IntegerData(required=False)
    ny = IntegerData()
    yn = IntegerData(default=10, required=False)
    yy = IntegerData(default=10)

class IntegerTestModel(DataModel):
    f = IntegerData()

class CharTestModel(DataModel):
    f = CharData()

class FloatTestModel(DataModel):
    f = FloatData()

class SlugTestModel(DataModel):
    t = CharData()
    f = SlugData(default_from='t')

class SlugTestModel2(DataModel):
    t = IntegerData(default=10)
    f = SlugData(default_from='t')

class ListTestModel(DataModel):
    f = ListData()

class DictTestModel(DataModel):
    f = DictData()

class ResourceTest(TestCase):
    def test_field_behavior(self):
        """
        | update | specified | default | required | what
        |   Y    |     N     |    N    |     N    | SKIP
        |   Y    |     N     |    N    |     Y    | SKIP
        |   Y    |     N     |    Y    |     N    | SKIP
        |   Y    |     N     |    Y    |     Y    | SKIP

        |   Y    |     Y     |    N    |     N    | USE
        |   Y    |     Y     |    N    |     Y    | USE
        |   Y    |     Y     |    Y    |     N    | USE
        |   Y    |     Y     |    Y    |     Y    | USE

        |   N    |     N     |    N    |     N    | SKIP
        |   N    |     N     |    N    |     Y    | ERROR
        |   N    |     N     |    Y    |     N    | DEFAULT
        |   N    |     N     |    Y    |     Y    | DEFAULT

        |   N    |     Y     |    N    |     N    | USE
        |   N    |     Y     |    N    |     Y    | USE
        |   N    |     Y     |    Y    |     N    | USE
        |   N    |     Y     |    Y    |     Y    | USE
        """
        m = FieldBehaviorTestModel()

        #Test updates, unspecified.
        self.assertEqual(m.validate({}, for_update=True), {})

        #Test updates, specified.
        self.assertEqual(m.validate({'nn': 1, 'ny': 2, 'yn': 3, 'yy': 4}, for_update=True), {'yy': 4, 'ny': 2, 'nn': 1, 'yn': 3})

        #Test inserts, unspecified.
        self.assertRaises(ValidationError, m.validate, {})
        try:
            m.validate({})
        except ValidationError as e:
            self.assertEqual({'ny': [u'This field is required.']}, e.message_dict)

        #Add the required key so that we can check defaults.
        self.assertEqual(m.validate({'ny': 3}), {'yy': 10, 'ny': 3, 'yn': 10})

        #Test inserts, specified.
        self.assertEqual(m.validate({'nn': 1, 'ny': 2, 'yn': 3, 'yy': 4}), {'nn': 1, 'ny': 2, 'yn': 3, 'yy': 4})

    def test_integerdata(self):
        m = IntegerTestModel()
        self.assertEqual(m.validate({'f': 1}), {'f': 1})
        self.assertEqual(m.validate({'f': '1'}), {'f': 1})
        self.assertRaises(ValidationError, m.validate, {'f': 1.06})
        self.assertRaises(ValidationError, m.validate, {'f': '1.06'})
        self.assertRaises(ValidationError, m.validate, {'f': 'b'})
        try:
            m.validate({'f': 'b'})
        except ValidationError as e:
            self.assertEqual({'f': [u'Enter a whole number.']}, e.message_dict)

    def test_chardata(self):
        m = CharTestModel()
        self.assertEqual(m.validate({'f': 1}), {'f': '1'})
        self.assertEqual(m.validate({'f': 'b'}), {'f': 'b'})
        self.assertEqual(m.validate({'f': 1.05}), {'f': '1.05'})
        self.assertEqual(m.validate({'f': None}), {'f': ''})
        self.assertEqual(m.validate({'f': False}), {'f': 'False'})

    def test_floatdata(self):
        m = FloatTestModel()
        self.assertEqual(m.validate({'f': 1}), {'f': 1})
        self.assertEqual(m.validate({'f': '1'}), {'f': 1})
        self.assertEqual(m.validate({'f': 1.06}), {'f': 1.06})
        self.assertEqual(m.validate({'f': '1.06'}), {'f': 1.06})
        self.assertRaises(ValidationError, m.validate, {'f': 'b'})

    def test_slugdata(self):
        m = SlugTestModel()
        self.assertRaises(ValidationError, m.validate, {'t': u'Hello There!', 'f': u'hello there'})
        self.assertEqual(m.validate({'t': 'Hello There!'}), {'t': u'Hello There!', 'f': u'hello-there'})

        #:TODO: Slug build from happens when defaults are processed, therefore they cannot be built from defaults.
        #m = SlugTestModel2()
        #print m.validate({})

    def test_listdata(self):
        m = ListTestModel()
        self.assertEqual(m.validate({'f': [1,2]}), {'f': [1,2]})
        self.assertRaises(ValidationError, m.validate, {'f': '234'})

    def test_dictdata(self):
        m = DictTestModel()
        self.assertEqual(m.validate({'f': {'g': 'h'}}), {'f': {'g': 'h'}})
        self.assertRaises(ValidationError, m.validate, {'f': []})

class EndpointTest(TestCase):
    urls = 'api.test_urls'

    def setUp(self):
        self.c = Client()

    def test_routing(self):
        self.assertEqual(self.c.get('/t1/').status_code, 200)
        self.assertEqual(self.c.post('/t1/', {1:2}).status_code, 405)
        self.assertEqual(self.c.delete('/t1/').content, 405)
        self.assertEqual(self.c.delete('/t1/').status_code, 405)
        self.assertEqual(self.c.options('/t1/').status_code, 405)
        self.assertEqual(self.c.patch('/t1/').status_code, 405)

    def test_echo(self):
        self.assertEqual(self.c.get('/t2/').content, '{\n  "hello": true\n}')
        self.assertEqual(self.c.get('/t2/').status_code, 200)

        self.assertEqual(json.loads(self.c.post('/t2/', {1:2}).content), {"1":"2"}) #We see a string conversion here because it's form-encoded.
        self.assertEqual(json.loads(self.c.post('/t2/', json.dumps({1:2}), content_type='application/json').content), {"1":2})
        self.assertEqual(self.c.post('/t2/', {1:2}).status_code, 200)

        self.assertEqual(self.c.put('/t2/', {1:2}).status_code, 200)
        self.assertEqual(json.loads(self.c.put('/t2/', {1:2}).content), {"1":"2"})
        self.assertEqual(json.loads(self.c.put('/t2/', json.dumps({1:2}), content_type='application/json').content), {"1":2})

        self.assertEqual(self.c.get('/t2/entity/').status_code, 200)
        self.assertEqual(self.c.get('/t2/entity/').content, '"entity"')

        self.assertEqual(json.loads(self.c.post('/t2/entity/', {1:2}).content), {u'1': u'2', u'id': u'entity'})
        self.assertEqual(json.loads(self.c.post('/t2/entity/', json.dumps({1:2}), content_type='application/json').content), {u'1': 2, u'id': u'entity'})

        self.assertEqual(self.c.put('/t2/entity/', {1:2}).status_code, 200)
        self.assertEqual(json.loads(self.c.put('/t2/entity/', {1:2}).content), {u'1': u'2', u'id': u'entity'})
        self.assertEqual(json.loads(self.c.put('/t2/entity/', json.dumps({1:2}), content_type='application/json').content), {u'1': 2, u'id': u'entity'})

        self.assertEqual(self.c.patch('/t2/entity/', {1:2}).status_code, 200)
        self.assertEqual(json.loads(self.c.patch('/t2/entity/', {1:2}).content), {u'1': u'2', u'id': u'entity'})
        self.assertEqual(json.loads(self.c.patch('/t2/entity/', json.dumps({1:2}), content_type='application/json').content), {u'1': 2, u'id': u'entity'})

    def test_middleware(self):
        #self.assertEqual(json.loads(self.c.post('/t2/', json.dumps({1:2}), content_type='application/json').content), {"1":2})
        self.assertEqual(json.loads(self.c.get('/t2/', {'format': 'json'}).content), {u'hello': True})
        self.assertEqual(self.c.get('/t2/', {'format': 'jsonp'}).status_code, 500)
        self.assertEqual(json.loads(self.c.get('/t2/', {'format': 'noformat'}).content), {u'hello': True}) #Falls back to JSON
        self.assertEqual(json.loads(self.c.get('/t2/', HTTP_ACCEPT='application/json').content), {u'hello': True})
        self.assertEqual(json.loads(self.c.get('/t2/', HTTP_ACCEPT='NOTHING/HERE').content), {u'hello': True})
        self.assertEqual(json.loads(self.c.get('/t2/', HTTP_ACCEPT='INVALID').content), {u'hello': True})
        self.assertEqual(self.c.get('/t2/', {'callback': 'hello'}).content, 'hello({\n  "hello": true\n})')
        #r = self.c.put('/t2/', {1:2})
        #print r.content
        #r = c.post('/api/test/', {'name': 'fred', 'age': 7})
        #print r.content
        #print r.status_code

    def test_validation(self):
        print self.c.get('/t3/', {'id': 302}).status_code
        print self.c.get('/t3/', {'id': 302}).content



















