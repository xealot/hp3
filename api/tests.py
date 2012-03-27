"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""

from django.test import TestCase
from data import *

class TestModel(DataModel):
    name = CharData(max_length=50, min_length=2)
    slug = SlugData(default_from='name', readonly=True)
    domains = ListData(min_length=1)
    priority = IntegerData(default=10)
    enabled = BooleanData(default=True)


class ResourceTest(TestCase):
    def test_fields(self):
        tm = TestModel()
        print tm.validate({'name': 'test'})
        #print tm
