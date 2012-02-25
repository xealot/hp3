from django.conf.urls import patterns, include, url

urlpatterns = patterns('',
    # Examples:
    # url(r'^$', 'hpt.views.home', name='home'),
    # url(r'^hpt/', include('hpt.foo.urls')),

    url(r'^api/', include('api.urls')),
)
