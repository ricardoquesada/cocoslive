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

def ipaddr_to_hex( ipaddr ):
    '''converts an ipaddress to it's hexadecimal representation to reduce memory on the memcache'''
    ret = '00000000'
    try:
        l = ipaddr.split('.')
        ints = map( lambda y: int(y), l )
        ret = '%02x%02x%02x%02x' % ( ints[0], ints[1], ints[2], ints[3] )
    except Exception, e:
        pass
    return ret

def getGeoIPCode(ipaddr):

    hex_ipaddr = ipaddr_to_hex( ipaddr)

    # use the 20 first bits for the cache.
    # it is assumed that the rest 12 bits belongs to the same country
    # this reduces queries and memory, and improves performance
    netmask = hex_ipaddr[0:5]

    # new memcache key (6 bytes)
    new_memcache_key = "%s" % netmask

    data = memcache.get(new_memcache_key)
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
    memcache.set(new_memcache_key, geoipcode, time)

    return geoipcode
