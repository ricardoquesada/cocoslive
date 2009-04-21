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
    No login is necessary
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
            value = getattr( e, f.name, '' )
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

    def get(self):
        '''HTTP GET request.
        Valid arguments:
            gamename: Name of the game. Required field
            offset: offset from the query. Default 0
            limit: how many scores to send back. Default 25
            category: category of the game
            order: desc or asc ?
            flags: flags for the query, like:only scores from country
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
        query.ancestor( self.game).filter('send = ', True)
        count = query.count()
        fields = query.fetch(limit=count)

        # convert the restuls to JSON format
        for r in results:
            self.entity_to_json(r, fields)

        # to comply with JSON parser in objective-c
        # a dictionary shall be the first element
        d = { 'scores' : self.json }

        # send back the info
        self.response.out.write( json.dumps( d ) )
        
#
# 'score/post' handler
#
class PostScore(BaseHandler):

    def validate_checksum( self ):
        '''validate checksum
        returns:
            True if checksum is OK
        '''
        hash = hashlib.md5()
        args = self.request.arguments()

        # sort in place
        args.sort()

        for arg in args:
            if arg.startswith('usr_'):
                str = self.request.get(arg).encode('utf-8')
                hash.update( str )
            elif (arg == 'cc_category' or arg == 'cc_score' or arg=='cc_playername'):
                str = self.request.get(arg).encode('utf-8')
                hash.update( str )

        hash.update( self.game.gamekey )

        bool = hash.hexdigest() == self.request.get('cc_hash')

        if not bool:
            self.response.set_status(400)
            self.response.out.write('Invalid hash value')

        return bool


    def cast_value_to_type( self, key, value ):
        '''cast a value to a certain type given it's key'''

        query = db.Query(ScoreField)
        query.filter('name = ', key).ancestor(self.game)
        result = query.fetch(1)[0]

        if result.type == 'int':
            return int(value)
        if result.type == 'float':
            return float(value)
        # don't cast strings... they are already strings
        return value

    
    def update_total_scores( self ):
        ''' updates the total number of scores.'''
        # Quantity of scores +1
        self.game.nro_scores +=1 
        self.game.put()

    def update_scores_by_country(self, score_country ):
        '''updates the total number of scores by country'''
        score_country.quantity += 1
        score_country.put()

    # XXX: possible race condition. use Model.get_or_insert() instead
    def get_or_create_country( self, country ):
        '''returns a new country if it doesn't exist or the current one if it exists'''
        query = db.Query(ScoresCountry)
        query.ancestor( self.game )
        query.filter('country_code =', country)
        result = query.fetch(limit=1)
        if query.count() > 0:
            score_country= result[0]
        else:
            score_country = ScoresCountry( parent=self.game, game=self.game, country_code=country, quantity=0 )
        return  score_country

    # This methods is run inside a transaction
    # All updates shall be done in the 'self.game' context
    def post_score( self, score, score_country ):

        # save score
        score.put()

        # update total scores
        self.update_total_scores()

        # update scores by country
        self.update_scores_by_country( score_country )


    def get(self):
        pass

    def post(self):
        '''HTTP POST handler'''

        if not self.validate_name( gamename = 'cc_gamename'):
            logging.error('Name validation failed')
            return

        if not self.validate_checksum():
            logging.error('Checksum validation failed')
            return

        score = Score( parent=self.game, cc_ip=self.request.remote_addr, cc_game=self.game)

        country = getGeoIPCode( self.request.remote_addr)
        country = country.strip()
        score.cc_country = country

        for arg in self.request.arguments():
            if arg.startswith('usr_') or arg =='cc_score' or arg=='cc_playername':
                value = self.request.get(arg)
                casted_value = self.cast_value_to_type( arg, value )
                setattr( score, arg, casted_value )

                if self.game.use_new_playername and arg=='usr_playername':
                    score.cc_playername = casted_value
        

        category = self.request.get('cc_category')
        if category:
            score.cc_category = category

        device_id = self.request.get('cc_device_id')
        if device_id:
            score.cc_device_id = device_id

        score_country = self.get_or_create_country( country )

        db.run_in_transaction( self.post_score,  score, score_country )

        # answer OK
        self.response.out.write('OK')

#
# 'score/update' handler
#
class UpdateScore(BaseHandler):

    def validate_checksum( self ):
        '''validate checksum
        returns:
            True if checksum is OK
        '''
        hash = hashlib.md5()
        args = self.request.arguments()

        # sort in place
        args.sort()

        for arg in args:
            if arg.startswith('usr_'):
                str = self.request.get(arg).encode('utf-8')
                hash.update( str )
            elif (arg == 'cc_category' or arg == 'cc_score' or arg=='cc_playername'):
                str = self.request.get(arg).encode('utf-8')
                hash.update( str )

        hash.update( self.game.gamekey )

        bool = hash.hexdigest() == self.request.get('cc_hash')

        if not bool:
            self.response.set_status(400)
            self.response.out.write('Invalid hash value')

        return bool


    def cast_value_to_type( self, key, value ):
        '''cast a value to a certain type given it's key'''

        query = db.Query(ScoreField)
        query.filter('name = ', key).ancestor(self.game)
        result = query.fetch(1)[0]

        if result.type == 'int':
            return int(value)
        if result.type == 'float':
            return float(value)
        # don't cast strings... they are already strings
        return value

    
    def update_total_scores( self ):
        ''' updates the total number of scores.'''
        # Quantity of scores +1
        self.game.nro_scores +=1 
        self.game.put()

    def update_scores_by_country(self, score_country ):
        '''updates the total number of scores by country'''
        score_country.quantity += 1
        score_country.put()

    # XXX: possible race condition
    def get_or_create_country( self, country ):
        '''returns a new country if it doesn't exist or the current one if it exists'''
        query = db.Query(ScoresCountry)
        query.ancestor( self.game )
        query.filter('country_code =', country)
        result = query.fetch(limit=1)
        if query.count() > 0:
            score_country= result[0]
        else:
            score_country = ScoresCountry( parent=self.game, game=self.game, country_code=country, quantity=0 )
        return  score_country

    # This methods is run inside a transaction
    # All updates shall be done in the 'self.game' context
    def update_score( self, score, score_country ):

        # save score
        score.put()

        if self.new_score:
            # update total scores
            self.update_total_scores()

            # update scores by country
            self.update_scores_by_country( score_country )

    # Get or create score
    # XXX: possible (but improbable) race condition
    def get_or_create_score( self ):
        category = self.request.get('cc_category')
        if not category:
            category = ''

        device_id = self.request.get('cc_device_id')
        if not device_id:
            logging.error('API update-scores: No cc_device_id')
            return None

        playername = self.request.get('cc_playername')
        if not playername:
            logging.error('API update-scores: No cc_playername')
            return None

        query = db.Query(Score)
        query.ancestor( self.game ).filter('cc_category =',category)
        query.filter('cc_playername =',playername)
        query.filter('cc_device_id =',device_id)

        score = query.fetch(limit=1)
        if not score:
            self.new_score = True
            score = Score( parent=self.game, cc_ip=self.request.remote_addr, cc_game=self.game, cc_playername=playername, cc_category=category, cc_device_id=device_id)
        else:
            score = score[0]
        return score


    def get(self):
        pass

    def post(self):
        '''HTTP POST handler'''

        if not self.validate_name( gamename = 'cc_gamename'):
            logging.error('Name validation failed')
            return

        if not self.validate_checksum():
            logging.error('Checksum validation failed')
            return

        self.new_score = False
        score = self.get_or_create_score()

        country = getGeoIPCode( self.request.remote_addr)
        country = country.strip()
        score.cc_country = country

        desc_score = False
        if self.game.scoreorder == 'desc':
            desc_score = True

        if not self.new_score:
            old_score = score.cc_score

        for arg in self.request.arguments():
            if arg.startswith('usr_') or arg =='cc_score':
                value = self.request.get(arg)
                casted_value = self.cast_value_to_type( arg, value )
                setattr( score, arg, casted_value )
      
        if self.new_score or (desc_score and score.cc_score > old_score) or (not desc_score and score.cc_score < old_score):
            score_country = self.get_or_create_country( country )
            db.run_in_transaction( self.update_score,  score, score_country )

        # answer OK
        self.response.out.write('OK')

application = webapp.WSGIApplication([
        ('/api/post-score', PostScore),
        ('/api/get-scores', GetScores),
        ('/api/update-score', UpdateScore),
        ],
        debug=True)


def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
