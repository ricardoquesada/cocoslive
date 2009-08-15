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
# If you are running your own instance of the server, you should replace
# geoutil.get_services() with a free service like:
#
#    services = ['http://geoip.wtanaka.com/cc/%s','http://abusebutler.appspot.com/loc/%s']
#    services = ['http://abusebutler.appspot.com/loc/%s','http://geoip.wtanaka.com/cc/%s']
#
# geoutil is not commited to the SVN because it contains the key used for the Geo IP service
#
import geoutil

__all__ = ['getGeoIPCode']

def getGeoIPCode(ipaddr):

    memcache_key = "gip_%s" % ipaddr
    data = memcache.get(memcache_key)
    if data is not None:
        return data
 
    services = geoutil.get_services()
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

    time = 60 * 60 * 24 * 30    # 30 days
    memcache.set(memcache_key, geoipcode, time)

    return geoipcode
