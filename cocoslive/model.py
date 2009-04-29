#!/usr/bin/env python
#
# cocos live - (c) 2009 Ricardo Quesada
# http://www.cocoslive.net
#
# License: GNU GPL v3
# See the LICENSE file
#

__docformat__ = 'restructuredtext'

from google.appengine.ext import db

__all__ = ['Developer', 'Game', 'Score', 'ScoreField', 'Category', 'ScoresCountry', 'DefaultValues' ]

#
# Model:
# A Developer can have many Games (Developer one-to-many Game )
# A Game can have many Scores (Game one-to-many Score)
#
class Developer(db.Model):
    #: user property
    user = db.UserProperty( required = True )

    #: Company Name
    name = db.StringProperty()

    #: developer homepage
    homepage = db.LinkProperty( default='http://example.com')

    #: icon
    icon = db.BlobProperty()

    #: creation date (useful?)
    creationdate = db.DateTimeProperty( auto_now_add=True )

    #: receive news letter
    receive_updates = db.BooleanProperty( default=False, required=True)

    def __str__(self):
        return str(self.user)


class Game(db.Model):
    #: who is the owner the the game
    owner = db.ReferenceProperty( Developer, collection_name='games' )

    #: game name
    name = db.StringProperty( required=True )

    #: game homepage
    homepage = db.LinkProperty( default='http://example.com' )

    #: App Store URL
    appstore = db.LinkProperty( default='http://www.example.com' )

    #: creation date (useful?)
    creationdate = db.DateTimeProperty( auto_now_add=True )

    #: game secret key. used to prevent spoofing
    gamekey = db.StringProperty(required=True)

    #: icon
    icon = db.BlobProperty()

    #: order
    scoreorder= db.StringProperty( default='desc' )

    #: Publish game in website
    publish = db.BooleanProperty( default=False )

    #: Number of Scores
    #: It is impossible with current GAE limitations to know if a query has more than 1000 entries
    nro_scores = db.IntegerProperty( default = 0)

    #: Featured game
    #: XXX: not used anymore
    featured = db.BooleanProperty( default=False, required=True)

    #: also copy usr_playername to cc_playername
    use_new_playername = db.BooleanProperty( default=False, required=True )

    #: supports rankings
    ranking_enabled = db.BooleanProperty( default=False, required=False)

    #: ranking: max score
    ranking_max_score = db.IntegerProperty( default=20000, required=False)

    #: ranking: max score
    ranking_min_score = db.IntegerProperty(default=0, required=False)

    #: ranking:
    ranking_branch_factor = db.IntegerProperty(default=100, required=False)

    def __str__(self):
        return str( self.name )

class Score(db.Expando):
    #: game that belongs
    cc_game = db.ReferenceProperty( Game, collection_name = 'scores' )

    #: iPhone device id (or any other id that identifies a unique device)
    cc_device_id = db.StringProperty( default = 'no_device' )

    #: category. A user defined category for the score. eg: 'medium', 'easy', 'difficulty'
    #: it is used to filter the queries. Give the top 20 scores with category 'easy'... etc.
    cc_category = db.StringProperty( default = '' )

    #: when
    cc_when = db.DateTimeProperty( auto_now_add=True )

    #: ip address
    cc_ip = db.StringProperty( required = True)

    #: country id (from ip_address)
    cc_country = db.StringProperty( default = '')

    #: player name. Store here the name/nick/id of the player
    cc_playername = db.StringProperty( default = '')

    #: score. It can later be changed to Float or String
#    cc_score = db.IntegerProperty()


class ScoreField(db.Model):
    #: game that belongs
    game = db.ReferenceProperty( Game, collection_name = 'score_fields' )

    #: field name
    name = db.StringProperty( required = True )

    #: field type
    type = db.StringProperty( required = True )

    #: send this field when requesting scores
    send = db.BooleanProperty( default = True, required = True )

    #: display this property on the WebPage
    displayweb = db.BooleanProperty( default = True, required = True )

    #: admin feature (can't be deleted)
    admin = db.BooleanProperty( required = True, default = False )


#
# Contains the different categories
#
class Category(db.Model):
    #: game that belongs
    game = db.ReferenceProperty( Game, collection_name = 'categories' )

    #: category name
    name = db.StringProperty( required = True )


#
# Scores by country
#
class ScoresCountry( db.Model ):
    #: game that belongs
    game = db.ReferenceProperty( Game, collection_name = 'nro_scores_country' )
    country_code = db.StringProperty( required = True)
    quantity = db.IntegerProperty( required = True )

#
# Default Values
#
class DefaultValues( db.Model ):
    # default game for games
    game_icon = db.BlobProperty()

    # default game for developers
    dev_icon = db.BlobProperty()
