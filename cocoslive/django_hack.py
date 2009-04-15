#!/usr/bin/env python
#
# cocos live - (c) 2009 Ricardo Quesada
# http://www.cocoslive.net
#
# License: GNU GPL v3
# See the LICENSE file
#

# python  imports
import string

# GAE imports
from google.appengine.ext import webapp

register = webapp.template.create_template_register()

def hash(h,key):
    if key in h:
        return h[key]
    else:
        return None

register.filter(hash)

def getattr (obj, args):
    """ Try to get an attribute from an object.

    Example: {% if block|getattr:"editable,True" %}

    Beware that the default is always a string, if you want this
    to return False, pass an empty second argument:
    {% if block|getattr:"editable," %}
    """

    splitargs = args.split(',')
    try:
        (attribute, default) = splitargs
    except ValueError:
        (attribute, default) = args, ''

    try:
        attr = obj.__getattribute__(attribute)
    except AttributeError:
        attr = obj.__dict__.get(attribute, default)
    except Exception, e:
        print e
        attr = default

    if hasattr(attr, '__call__'):
        return attr.__call__()
    else:
        return attr

register.filter(getattr)


def getfield(obj, arg):
    ret = getattr(obj,arg)
    if not ret:
        ret = eval('obj.%s' % arg)
    return ret

def prettyfield(obj):
    ret = obj.split('_')
    if not ret:
        return obj

    if len(ret) > 2:
        ret = string.join(ret[1:],'_')
    else:
        ret = ret[1]
    return ret

register.filter(getfield)
register.filter(prettyfield)
