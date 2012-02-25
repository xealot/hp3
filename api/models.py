from mongoengine import *
from datetime import datetime
from django.utils.functional import curry
from lib.utilities import random_password
from lib.mongoengine_extras import Validating, AutoSlugField


class ContactBase(EmbeddedDocument, Validating):
    email = EmailField()
    title = StringField()
    prefix = StringField()
    firstname = StringField()
    middlename = StringField()
    lastname = StringField()
    suffix = StringField()
    phone = StringField()
    birthdate = StringField()
    note = StringField()
    addr_street = StringField()
    addr_street2 = StringField()
    addr_locality = StringField()
    addr_region = StringField()
    addr_country = StringField()


class System(Document, Validating):
    name = StringField(required=True, max_length=75)
    slug = AutoSlugField(populate_from='name', unique=True, required=True, max_length=75)


class User(Document, Validating):
    system = ReferenceField(System, required=False, default='', reverse_delete_rule=DO_NOTHING)
    email = EmailField(unique_with='system', required=True)
    name = StringField(required=True, max_length=75)
    remote_id = StringField(max_length=100)
    created_on = DateTimeField(default=datetime.utcnow)
    login_on = DateTimeField()
    api_token = StringField(default=curry(random_password, 20, 35))
    contact = EmbeddedDocumentField(ContactBase)


class Contact(Document):
    contact = EmbeddedDocumentField(ContactBase)
    custom = DictField()
    tags = ListField()
    origin = StringField()
    created_on = DateTimeField(default=datetime.utcnow)
    viewed_on = DateTimeField()
