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
from google.appengine.api import datastore
from google.appengine.api import datastore_errors
from google.appengine.api import datastore_types
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp.util import run_wsgi_app
from ranker.common import transactional

# 3rd partly libs
import simplejson as json

# local imports
from model import Game, Score, ScoreField, ScoresCountry 
from util import *

from ranker import ranker


class BaseHandler( webapp.RequestHandler):

    def __init__(self):
        super( BaseHandler, self ).__init__()
        self.game = None
        self.game_name = ''

    def get_ranker( self, game_key, category ):
        key = datastore_types.Key.from_path("Ranking", category, parent=game_key )
        return ranker.Ranker(datastore.Get(key)["ranker"])

    def get_or_create_ranker( self, game_key, category ):
        key = datastore_types.Key.from_path("Ranking", category, parent=game_key )
        try:
            return ranker.Ranker(datastore.Get(key)["ranker"])
        except datastore_errors.EntityNotFoundError:
            r = ranker.Ranker.Create([self.game.ranking_min_score, self.game.ranking_max_score], self.game.ranking_branch_factor)
            app = datastore.Entity("Ranking", name=category, parent=game_key )
            app["ranker"] = r.rootkey
            datastore.Put(app)
            return r



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
            raise Exception("GetScores: limit can't be greater than 100")

        if self.game.ranking_enabled and limit > 40:
            raise Exception("GetScores: limit can't be greater than 40 when rankings are enabled")

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

    def update_json_with_positions( self, ranker ):
        scores = map(lambda y: [y['cc_score']], self.json )
        ranks = ranker.FindRanks( scores )

        for i,item in enumerate(self.json):
            # ranker are 0-based. Make it 1-based
            item['position'] = ranks[i] + 1

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
            raise Exception("GetScores: Name validation failed")

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
                logging.error('API get-scores: Cannot locate country for current IP. Game: %s' % self.game_name)
                raise Exception("GetScores: Cannot locate country for current IP address")

        # device and country can't be at the same time
        elif QueryFlagByDevice & flags:
            device = self.get_device_id()
            if device:
                query.filter('cc_device_id = ', device)
            else:
                logging.error('API get-scores: Device parameter missing. Game: %s' % self.game_name)
                raise Exception("GetScores: Device parameter is missing")

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

        if self.game.ranking_enabled:
            ranker = self.get_ranker( self.game.key(), category )
            self.update_json_with_positions( ranker )

        # to comply with JSON parser in objective-c
        # a dictionary shall be the first element
        d = { 'scores' : self.json }

        # send back the info
        self.response.out.write( json.dumps( d ) )


class GetRankForScore(BaseHandler):
    '''Handles the HTTP GET request to obtain the global ranking of name + device
    No login is necessary
    '''

    def __init__(self):
        super( GetRankForScore, self ).__init__()
        self.json = []
        self.position = 0

    def get(self):
        '''HTTP GET request.
        Needed arguments:
            gamename: Name of the game. Required field
            name: name of the player 
            device: device id 
        '''
        if not self.validate_name():
            logging.error('API get-rank-for-score: Name validation failed')
            raise Exception("GetRankForScore: Name validation failed")

        if not self.game.ranking_enabled:
            logging.error('API get-rank-for-score: game does not support ranking')
            raise Exception("GetRankForScore: game does not support ranking")

        category = self.request.get('category')
        if category is None:
            category = ''

        score = self.request.get('score')
        score = int(score)
        ranker = self.get_ranker( self.game.key(), category )
        rank = ranker.FindRank( [score] )
        self.response.out.write('OK: %d' % (rank + 1) )

class GetRanksForScores(BaseHandler):
    '''Handles the HTTP GET request to obtain the global ranking of name + device
    No login is necessary
    '''

    def __init__(self):
        super( GetRanksForScores, self ).__init__()
        self.json = []
        self.position = 0

    def get(self):
        '''HTTP GET request.
        Needed arguments:
            gamename: Name of the game. Required field
            name: name of the player 
            device: device id 
        '''
        if not self.validate_name():
            logging.error('API get-ranks-for-score: Name validation failed')
            raise Exception("GetRanksForScores: Name validation failed")

        if not self.game.ranking_enabled:
            logging.error('API get-ranks-for-scores: game does not support ranking')
            raise Exception("GetRanksForScores: game does not support ranking")

        category = self.request.get('category')
        if category is None:
            category = ''

        scores = self.request.get('scores')
        scores = scores.split(',')
        scores = map(lambda y: [int(y)], scores)
        ranker = self.get_ranker( self.game.key(), category )
        ranks = ranker.FindRanks( scores )
        ranks = map(lambda y:int(y)+1, ranks)
        self.response.out.write('OK: %s' % str(ranks) )

class GetScoreForRank(BaseHandler):
    '''Handles the HTTP GET request to obtain the global ranking of name + device
    No login is necessary
    '''

    def __init__(self):
        super( GetScoreForRank, self ).__init__()
        self.json = []
        self.position = 0

    def get(self):
        '''HTTP GET request.
        Needed arguments:
            gamename: Name of the game. Required field
            name: name of the player 
            device: device id 
        '''
        if not self.validate_name():
            logging.error('API get-score-for-rank: Name validation failed')
            raise Exception("GetScoreForRank: Name validation failed")

        if not self.game.ranking_enabled:
            logging.error('API get-score-for-rank: game does not support ranking')
            raise Exception("GetScoreForRank: game does not support ranking")

        category = self.request.get('category')
        if category is None:
            category = ''

        rank = self.request.get('rank')
        rank = int(rank)
        ranker = self.get_ranker( self.game.key(), category )
        score = ranker.FindScore( rank )
        self.response.out.write('OK: %d %d' % (score[0][0], score[1]) )
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
    @transactional
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
            logging.error('API post-score: Name validation failed')
            raise Exception("PostScore: Name validation failed")

        if self.game.ranking_enabled:
            logging.error('API post-score: Ranking support is not enabled with "new score" yet')
            raise Exception("PostScore: Ranking support is not enabled with 'new score' yet")


        if not self.validate_checksum():
            logging.error('API post-score: Checksum validation failed. Game: %s' % self.game_name)
            raise Exception("PostScore: Checksum validation failed")

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

        # runs in trasaction
        self.post_score( score, score_country )

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
    @transactional
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

        self.category = category

        device_id = self.request.get('cc_device_id')
        if not device_id:
            logging.error('API update-score: No cc_device_id in game: %s' % self.game_name )
            raise Exception("UpdateScore failed: no cc_device_id")

        playername = self.request.get('cc_playername')
        if playername is None:
            logging.error('API update-score: No cc_playername in game: %s' % self.game_name )
            raise Exception("UpdateScore failed: no cc_playername")

        # needed for rankings
        self.profile_id = "%s@%s" % (playername, device_id)

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
            logging.error('API udpate-score: Name validation failed.')
            raise Exception("UpdateScore: Name validation failed")

        if not self.validate_checksum():
            logging.error('API update-score: Checksum validation failed: %s' % self.game_name)
            raise Exception("UpdateScore: Checksum failed")

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
     
        score_updated = False
        if self.new_score or (desc_score and score.cc_score > old_score) or (not desc_score and score.cc_score < old_score):
            score_country = self.get_or_create_country( country )

            # runs in transaction
            self.update_score( score, score_country )
            score_updated = True

            if self.game.ranking_enabled:
                # BUG XXX should run in another transaction
                ranker = self.get_or_create_ranker( self.game.key(), self.category )
                ranker.SetScore( self.profile_id, [score.cc_score])


        if self.game.ranking_enabled:
            ranker = self.get_ranker( self.game.key(), self.category )
            rank = ranker.FindRank( [score.cc_score] )
            self.response.out.write('OK:ranking=%d,score_updated=%d' % (rank+1, score_updated) )
        else:
            self.response.out.write('OK')


application = webapp.WSGIApplication([
        ('/api/post-score', PostScore),
        ('/api/update-score', UpdateScore),
        ('/api/get-scores', GetScores),
        ('/api/get-rank-for-score', GetRankForScore),
        ('/api/get-ranks-for-scores', GetRanksForScores),
        ('/api/get-score-for-rank', GetScoreForRank),
        ],
        debug=True)


def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
