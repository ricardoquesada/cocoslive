#!/usr/bin/env python
#
# cocos live - (c) 2009 Ricardo Quesada
# http://www.cocoslive.net
#
# License: GNU GPL v3
# See the LICENSE file
#

# python imports
import datetime
import logging

# GAE imports
from google.appengine.ext import bulkload
from google.appengine.api import datastore_types
from google.appengine.ext import search
from google.appengine.ext import db

# local imports
from model import *
from util import *

class ScoreLoader(bulkload.Loader):
    def __init__(self):

#        game = Game.get_by_key_name('Sapus Tongue')
#        for score in game.scores:
#            score.delete()
#        adfaf

        bulkload.Loader.__init__(self, 'Score',
                            [('usr_playername', str),
                            ('cc_score',int),
                            ('usr_playertype',int),
                            ('cc_device_id',str),
                            ('cc_ip',str),
                            ('cc_when', lambda x: datetime.datetime.strptime(x,'%Y-%m-%d %H:%M:%S') ),
                            ('usr_angle', int),
                            ('usr_speed', int),
                            ])

    def HandleEntity(self, entity):

        game = Game.get_by_key_name('Sapus Tongue')

        country = getGeoIPCode( entity['cc_ip'])

        game.nro_scores += 1
        game.put()

        query = db.Query(ScoresCountry)
        query.ancestor( game )
        query.filter('country_code =', country)
        result = query.fetch(limit=1)
        if query.count() > 0:
            rec = result[0]
            rec.quantity += 1
        else:
            rec = ScoresCountry( parent=game, game=game, country_code=country, quantity=1 )
        rec.put()

        return None

if __name__ == '__main__':
    bulkload.main(ScoreLoader())
