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


__all__ = ['getGeoIPCode']

def getGeoIPCode(ipaddr):

    memcache_key = "gip_%s" % ipaddr
    data = memcache.get(memcache_key)
    if data is not None:
        return data
  
    services = ['http://geoip.wtanaka.com/cc/%s','http://abusebutler.appspot.com/loc/%s']
#    services = ['http://abusebutler.appspot.com/loc/%s','http://geoip.wtanaka.com/cc/%s']
    geoipcode = ''

    for service in services:
        try:
            fetch_response = urlfetch.fetch( service % ipaddr)
            if fetch_response.status_code == 200:
                geoipcode = fetch_response.content

            geoipcode = geoipcode.strip().lower()
            if geoipcode == 'none' or geoipcode =='':
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

    memcache.set(memcache_key, geoipcode)

    return geoipcode
