from default import *
#from mongoengine import connect
#from pymongo import Connection, ReadPreference

INSTALLED_APPS += (
    'api',
)

#MONGO_DATABASE = 'homeplate'
#MONGO_CONNECTION_PARAMS = dict(
#    host='ubuntu.local',
#    port=27017,
#    network_timeout=20,
#    tz_aware=True,
#    read_preference=ReadPreference.SECONDARY
#)

#connect('homeplate', host='ubuntu.local', tz_aware=True)
#end_request in a middleware