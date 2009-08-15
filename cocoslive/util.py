#!/usr/bin/env python
#
# cocos live - (c) 2009 Ricardo Quesada
# http://www.cocoslive.net
#
# License: GNU GPL v3
# See the LICENSE file
#
__docformat__ = 'restructuredtext'

# GAE imports
from google.appengine.api import urlfetch
from google.appengine.api import memcache


# IMPORTNAT:
# geoutil contains the an URL with a secret key used to parse the geo ip from a paid service
# so, geoutil it's not commited
# If geoutil is not found, it will use free Geo IP services (which are somewhat slower)
#
try:
    from geoutil import get_services
except Exception, e:
    from geoutil_public import get_services

__all__ = ['getGeoIPCode']

def getGeoIPCode(ipaddr):

    memcache_key = "gip_%s" % ipaddr
    data = memcache.get(memcache_key)
    if data is not None:
        return data
 
    services = get_services()
    geoipcode = ''

    for service in services:
        try:
            fetch_response = urlfetch.fetch( service % ipaddr)
            if fetch_response.status_code == 200:
                geoipcode = fetch_response.content

            geoipcode = geoipcode.strip().lower()
            if geoipcode.startswith('(null)') or geoipcode == 'none' or geoipcode =='':
                geoipcode = ''
                continue
            else:
                break
        except urlfetch.Error, e:
            continue

    if geoipcode:
        # convert to lower case, and store in mem cache
        if geoipcode == '':
            geoipcode = 'xx'
    else:
        geoipcode = 'xx'

#    time = 60 * 60 * 24 * 30    # 30 days
    time = 0                # never expires
    memcache.set(memcache_key, geoipcode, time)

    return geoipcode
