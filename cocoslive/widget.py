#!/usr/bin/env python
#
# cocos live - (c) 2009 Ricardo Quesada
# http://www.cocoslive.net
#
# License: GNU GPL v3
# See the LICENSE file
#

__docformat__ = 'restructuredtext'

# python imports
import os
import datetime
import hashlib
import logging

# GAE imports
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp.util import run_wsgi_app

# 3rd partly libs
import simplejson as json

# local imports
from model import Game, Score, ScoreField, ScoresCountry
from util import *


class BaseHandler( webapp.RequestHandler):

    def __init__(self):
        super( BaseHandler, self ).__init__()
        self.game = None
        self.game_name = ''

    def validate_name(self, gamename ='gamename'):
        '''validate authentication
        returns:
            True if validation is OK
        '''
        self.game_name = self.request.get(gamename)
        if not self.game_name:
            self.response.set_status(400)
            self.response.out.write('variable %s not found' % gamename)
            return False

        self.game = Game.get_by_key_name( self.game_name )
        if not self.game:
            self.response.set_status(400)
            self.response.out.write('game not found %s' % self.game_name)
            return False
        return True

#
# get scores
#

#
# XXX: These macros MUST be synced with ScoreServerRequest.h
#
# Query type:
QueryIgnore, QueryDay, QueryWeek, QueryMonth, QueryAllTime = xrange(5)
#
# Query flags:
QueryFlagNone = 0
QueryFlagByCountry = 1 << 0
QueryFlagByDevice = 1 << 1


class GetScores(BaseHandler):
    '''Handles the HTTP GET request to obtain the high scores
    No login is necessary.
    The Scores are encoded in JSONP
    '''

    def __init__(self):
        super( GetScores, self ).__init__()
        self.json = []
        self.position = 0


    def entity_to_json(self, e, fields):
        '''Converts an entity to JSON format'''
        d = {}
        for f in fields:
            key = f.name
            value = getattr( e, f.name )
            d[key] =  value

        d['position'] = self.position
        self.json.append( d )
        self.position += 1

    def get_offset(self):
        '''Get the offset argument. Default 0'''
        offset = self.request.get('offset')
        if not offset:
            offset = 0
        else:
            offset = int(offset)
        self.position = offset
        return offset

    def get_limit(self):
        '''Get the limit argument. Default 25. Maximum limit is 100'''
        limit = self.request.get('limit')
        if not limit:
            limit = 25
        else:
            limit = int(limit)

        if limit > 100:
            limit = 100

        return limit

    def get_category(self):
        '''Get the category argument. Default \'\''''
        category = self.request.get('category')
        if not category:
            category = ''
        return category

    def get_order(self):
        '''Get the order argument. Default 0'''
        if self.game.scoreorder == 'desc':
            return '-cc_score'
        return 'cc_score'

    def get_query_type(self):
        '''Get query type. Default: All time'''
        query_type = self.request.get('querytype')

        now = datetime.datetime.now()
        if not query_type:
            query_type = QueryAllTime
        else:
            query_type = int(query_type)

        if query_type == QueryDay:
            delta = datetime.timedelta(days=1)
        elif query_type == QueryWeek:
            delta = datetime.timedelta(weeks=1)
        elif query_type == QueryMonth:
            delta = datetime.timedelta(days=30)
        else:
            delta = None

        if delta:
            return now - delta
        return None

    def get_query_flags(self):
        '''Get flags'''
        ret_flags = []
        flags = self.request.get('flags')
        if flags:
            return int(flags)
        return 0

    def get_device_id(self):
        '''Get the device ID'''
        return self.request.get('device')

    def get_json_callback(self):
        '''returns the name of the JSON callback'''
        json_cb = self.request.get('jsoncallback')
        if not json_cb:
            json_cb = 'jsonCocosLiveFeed'
        return json_cb

    def get(self):
        '''HTTP GET request.
        Valid arguments:
            gamename: Name of the game. Required field
            offset: offset from the query. Default 0
            limit: how many scores to send back. Default 25
            category: category of the game
            order: desc or asc ?
            flags: flags for the query, like:only scores from country
            device: filter by this device
            jsonCallback: JSONP callback function
        '''
        if not self.validate_name():
            logging.error('API get-scores: Name validation failed')
            return

        offset = self.get_offset()
        limit = self.get_limit()
        category = self.get_category()
        order = self.get_order()
        dates = self.get_query_type()
        flags = self.get_query_flags()
        jsonCallback = self.get_json_callback()

        # sort the scores by the score field
        query = db.Query(Score)
        query.ancestor( self.game ).filter('cc_category =',category)

        # only by country ?
        if QueryFlagByCountry & flags:
            country = getGeoIPCode( self.request.remote_addr)
            if country:
                query.filter('cc_country =', country)
            else:
                logging.error('API get-scores: Cannot locate country for current IP')
                return

        # device and country can't be at the same time
        elif QueryFlagByDevice & flags:
            device = self.get_device_id()
            if device:
                query.filter('cc_device_id = ', device)
            else:
                logging.error('API get-scores: Device parameter missing')
                return

        #if dates:
        #    query.filter('cc_when >', dates)
        query.order(order)
        results = query.fetch(limit=limit, offset=offset)
        
        # filter the fields to send to the usr
        query = db.Query(ScoreField)
        query.ancestor( self.game).filter('send =', True)
        count = query.count()
        fields = query.fetch(limit=count)

        # convert the restuls to JSON format
        for r in results:
            self.entity_to_json(r, fields)

        # to comply with JSON parser in objective-c
        # a dictionary shall be the first element
        d = { 'scores' : self.json }

        # send back the info
        self.response.out.write( "%s(%s)" % (jsonCallback, json.dumps( d ) ) )
        

application = webapp.WSGIApplication([
        ('/widget/get-scores', GetScores),
        ],
        debug=True)


def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
