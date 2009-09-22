#!/usr/bin/env python
#
# cocos live - (c) 2009 Ricardo Quesada
# http://www.cocoslive.net
#
# License: GNU GPL v3
# See the LICENSE file

#
# Everything related to the user (developer) actions:
#    Edit game
#    Edit developer properties
#    Create Game
#    etc..
#

__docformat__ = 'restructuredtext'

# python imports
import os
import datetime
import hashlib
import random
import logging
import functools

# GAE imports
from google.appengine.api import datastore
from google.appengine.api import datastore_errors
from google.appengine.api import datastore_types
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import login_required
from google.appengine.ext.webapp import template
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.api import images

# 3rd partly libs
import simplejson as json

# local imports
from model import Developer, Game, Score, ScoreField, Category, ScoresCountry
from util import *
import configuration
from ranker import ranker
from ranker.common import transactional

def owner_of_game_required(func):
    """Ensure that the logged in user is the owner of the game."""

    @functools.wraps(func)
    def __wrapper(self, *args, **kwds):
        """Makes it possible for super_user_required to be used as a decorator."""

        user = users.get_current_user()
        if not user:
            logging.error('Fobidden: must be logged in')
            return self.forbidden('You must be logged in')

        dev = Developer.get_by_key_name( user.email() )
        if not dev:
            loggin.error('Forbidden: developer unknwon')
            return self.forbidden('Developer Unknwon')

        name = self.request.get('gamename')
        if not name:
            logging.error('Fobidden: gamename not found')
            return self.forbidden('Gamename not found')

        # ADMIN can edit other users games
        if not users.is_current_user_admin():

            game = dev.games.filter( 'name =', name )
            if not game:
                logging.error('Forbidden: game does not belong to you')
                return self.forbidden('Game does not belong to you')

            game_instance = game.get()
            if not game_instance:
                logging.error('Forbidden: game does not belong to you')
                return self.forbidden('Game does not belong to you')

        return func(self, *args, **kwds)

    return __wrapper


class BaseHandler( webapp.RequestHandler):
    def respond(self, templatename, params=None):
        """Helper to render a response.

          This function assumes that the user is logged in.

          Args:
            self: The handler object
            templatename: The template name; '.html' is appended automatically.
            params: A dict giving the template parameters; modified in-place.

          Returns:
            Whatever render_to_response(template, params) returns.

          Raises:
            Whatever render_to_response(template, params) raises.
        """
        if params is None:
            params = {}

        user = users.get_current_user()
        if user:
            params['user'] = user
            params['sign_out'] = users.CreateLogoutURL('/')
            params['is_admin'] = users.is_current_user_admin()
        else:
            params['sign_in'] = users.CreateLoginURL('/user/create-user')

        if hasattr(self, 'profile'):
            profile = request.profile
##    params['sidebar'] = models.Sidebar.render(profile)
            params['is_superuser'] = profile.is_superuser
        params['configuration'] = configuration

        if not templatename.endswith('.html'):
            templatename += '.html'
        templatename = 'templates/%s' % templatename

        return self.response.out.write( template.render(templatename, params) )


    def forbidden(self, error_message=None):
        """Returns a 403 response based on a template.

        Args:
            request: the http request that was forbidden
            error_message: a message to display that will override the default message

        Returns:
            A http response with the status code of 403

        """
        params = { 'error_message' : error_message }
        return self.respond('403', params )


    def page_not_found(self, error_message=None):
        """Returns a 404 response based on a template.
        Args:
          request: the http request that was forbidden
          error_message: a message to display that will override the default message

        Returns:
            A http response with the status code of 404
        """
        params = { 'error_message' : error_message }
        return self.respond('404', params )

    def get_user_data(self):
        """test whether or not the Developer was created"""
        user = users.get_current_user()
        if user:
            dev = Developer.get_by_key_name( user.email() )
            return dev
        # else
        return None

    def create_user_data(self):
        """Create the Developer"""
        user = users.get_current_user()
        if user:
            dev = Developer( key_name=user.email(), user=user, name='John Doe', homepage='http://example.com')
            dev.put()
        else:
            pass

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
#
# '/create-user' handler
#
class CreateUser(BaseHandler):

    @login_required
    def get(self):
        if not self.get_user_data():
            self.create_user_data()

        self.redirect('/')

#
# 'user/games' handler
#
class ListGames(BaseHandler):
    @login_required
    def get(self):

        user = users.get_current_user()
        dev = Developer.get_by_key_name( user.email() )
        games = dev.games.order('creationdate')

        params = {
            'games' : games,
            'page' : {'title' : 'Your Games'},
        }
        self.respond('list-games', params)

#
# 'user/game/create' handler
#
class CreateGame(BaseHandler):

    @login_required
    def get(self):

        # Since "Add New Game" is in the main page
        # this check shall be added
        if not self.get_user_data():
            self.create_user_data()

        params = {
                'page' : {'title' : 'Create New Game' },
        }

        self.respond('create-game', params )


    def post(self):
        user = users.get_current_user()
        if not user:
            logging.error('CreateGame: You must be logged in')
            self.forbidden('CreateGame: You must be logged in to perform this action')
            return

        name = self.request.get("name")
        score_type = self.request.get("score_type")
        homepage = self.request.get("homepage")

        dev = Developer.get_by_key_name(user.email() )
        if not dev:
            logging.error('CreateGame: Create an account first')
            self.forbidden('CreateGame: Create an account first to perform this action')
            return

        if not self.validate_game_name( name ):
            logging.error('CreateGame: Game already exists')
            self.forbidden('CreateGame: Game Already exists. Try with another game')
            return

        if not self.validate_score_type( score_type ):
            logging.error('CreateGame: invalid score type')
            self.forbidden('CreateGame: invalid score type')
            return

        gamekey = hashlib.md5( str(random.random()) ).hexdigest()
        self.response.out.write( name )
        game = Game(key_name=name,
                    name=name,
                    owner=dev,
                    gamekey=gamekey,
                    homepage=homepage,
                    )

        game.put()

        self.add_default_category( game )
        self.create_game_table( name, game, score_type )
        self.redirect('/user/edit-game?gamename=%s'% name)


    def validate_score_type( self, score_type ):
        return score_type in ['int','float','string']

    def validate_game_name( self, name ):
        g = Game.get_by_key_name(name)
        if g:
            return False
        return True

    def add_default_category( self, game ):
        cat = "Classic"
        category = Category( key_name=cat, name=cat, parent=game, game=game)
        category.put()

    def create_game_table( self, name, game, score_type):
        # device id
        field = ScoreField( key_name='cc_device_id', name='cc_device_id', type='string', admin=True, send=False, displayweb=False, parent=game, game=game)
        field.put()

        # game name
        field = ScoreField( key_name='cc_game', name='cc_game', type='string', admin=True, send=False, displayweb=False, parent=game, game=game)
        field.put()

        # IP Address
        field = ScoreField( key_name='cc_ip', name='cc_ip', type='string', admin=True, send=False, displayweb=False, parent=game, game=game)
        field.put()

        # country
        field = ScoreField( key_name='cc_country', name='cc_country', type='string', admin=True, send=True, displayweb=True, parent=game, game=game)
        field.put()

        # datetime
        field = ScoreField( key_name='cc_when', name='cc_when', type='date', admin=True, send=False, displayweb=True, parent=game, game=game)
        field.put()

        # category
        field = ScoreField( key_name='cc_category', name='cc_category', type='string', admin=True, send=False, displayweb=False, parent=game, game=game)
        field.put()

        # score
        field = ScoreField( key_name='cc_score', name='cc_score', type=score_type, admin=True, send=True, displayweb=True, parent=game, game=game)
        field.put()

        # playername
        field = ScoreField( key_name='cc_playername', name='cc_playername', type='string', admin=True, send=True, displayweb=True, parent=game, game=game)
        field.put()

#
# 'user/game/status' handler
#
class GameStatus(BaseHandler):

    @owner_of_game_required
    def get(self):
        user = users.get_current_user()
        if user:
            game = self.request.get("gamename")
            game = Game.get_by_key_name( game )
            scores = game.scores

            fields = game.score_fields
          
            values = {
                'fields' : fields,
                'scores' : scores,
                'game' : game,
            }
            self.response.out.write( template.render('templates/game-status.html', values) )

        else:
            self.response.set_status(401)
            self.response.out.write('you must be logged in')


class EditDeveloper(BaseHandler):

    @login_required
    def get(self):
        user = users.get_current_user()
        if not user:
            logging.error('EditDeveloper: get user failed')
            return self.forbidden('User not found')

        dev = Developer.get_by_key_name( user.email() )
        if not dev:
            logging.error('EditDeveloper: Developer not found')
            return self.forbidden('Developer not found')

        params = {
            'dev' : dev,
            'page' : {'title' : 'Edit Developer: %s' % dev.user },
        }
        self.respond('dev-edit', params)


    def post(self):
        '''HTTP POST handler'''

        # get current user
        user = users.get_current_user()
        if not user:
            logging.error('EditDeveloper POST: get user failed')
            return self.forbidden('You must be logged in')

        # obtain developer id
        dev = Developer.get_by_key_name( user.email() )
        if not dev:
            logging.error('EditDeveloper POST: Developer not found')
            return self.forbidden('Developer not found. Contact system administrator')


        # type of POST
        type = self.request.get('type')
        if type == 'update_properties':
            self.update_properties( dev )
        else:
            logging.error('EditDeveloper POST: Type not found')
            return self.forbidden('Type update_properties not found')

        self.redirect('/user/edit-dev')

    # Update game properties
    def update_properties( self, dev ):
        # new icon ?
        icon = self.request.get("icon")
        if icon:
            icon = images.resize( icon,57,57)
            dev.icon = db.Blob(icon)

        # new homepage ?
        homepage = self.request.get('homepage')
        if homepage:
            dev.homepage = homepage 

        # company name 
        name = self.request.get('name')
        if name:
            dev.name = name 

        # updates by email
        updates = self.request.get('receive_updates')
        if updates:
            updates = (updates == 'True' )
            dev.receive_updates = updates

        dev.put()


class EditGame(BaseHandler):

    @owner_of_game_required
    def get(self):
        user = users.get_current_user()
        if user:
            gamename = self.request.get("gamename")
            game = Game.get_by_key_name( gamename )

            fields = game.score_fields
            categories = game.categories

            params = {
                'fields' : fields,
                'game' : game,
                'categories' : categories,
                'page' : {'title' : 'Edit Game: %s' % gamename },
            }
            self.respond('game-edit', params)


        else:
            self.response.set_status(401)
            self.response.out.write('you must be logged in')


    @owner_of_game_required
    def post(self):
        '''HTTP POST handler'''

        # get current user
        user = users.get_current_user()
        if not user:
            logging.error('User not found')
            return

        # obtain developer id
        dev = Developer.get_by_key_name( user.email() )
        if not dev:
            logging.error('Developer not found')
            return 

        # obtain game name
        gamename = self.request.get('gamename')
        if not gamename:
            logging.error('Gamename not found')
            return

        # game belongs to developer ?
        game = Game.get_by_key_name( gamename )
#        game = dev.games.filter( 'name =', gamename ).fetch(limit = 1)[0]
        if not game:
            logging.error('Game not found')
            return 

        # type of POST
        type = self.request.get('type')
        if type == 'update_properties':
            self.update_properties( game )
        elif type == 'new_field':
            self.new_field( game )
#        elif type == 'new_score_type':
#            self.new_score_type( game )
        elif type == 'new_category':
            self.new_category( game )
        elif type == 'update_displayweb':
            self.update_displayweb( game )
        elif type == 'use_new_playername':
            self.use_new_playername( game )
        elif type == 'enable_ranking':
            self.enable_ranking( game )
        else:
            logging.error('Type not found')
            self.error(404)

        self.redirect('/user/edit-game?gamename=%s' % gamename )

    # enable ranking
    def enable_ranking( self, game ):
        if game.ranking_enabled:
            raise Exception("Ranking is already enabled")

        if game.nro_scores != 0:
            raise Exception("Delete all the game scores to enable rankings")

        if game.scoreorder != 'desc':
            raise Exception("Ranking only works with Descending scores")

        enabled = (self.request.get('rank_enabled') == 'True' )

        min = self.request.get('rank_min_score')
        max = self.request.get('rank_max_score')
        min = int(min)
        max = int(max)

        game.ranking_min_score = min
        game.ranking_max_score = max
        game.ranking_enabled = enabled
        game.put()


    # use (or don't use) new playername
    def use_new_playername(self, game ):
        new_playername = self.request.get('new_playername')
        new_playername = ( new_playername == 'True' )

        game.use_new_playername = new_playername
        game.put()

        field = game.score_fields.filter('name =', 'cc_playername').fetch(1)
        if not field:
            field = ScoreField( key_name='cc_playername', name='cc_playername', type='string', admin=True, send=True, displayweb=True, parent=game, game=game)
            field.put()

    # New category
    def new_category( self, game ):
        # new category to game
        cat = self.request.get('category')
        if cat:
            category = Category( key_name=cat, name=cat, parent=game, game=game)
            category.put()
        else:
            logging.error('EditGame POST: missing category')

    # Update game properties
    def update_properties( self, game ):
        # new icon ?
        icon = self.request.get("icon")
        if icon:
            icon = images.resize( icon,57,57)
            game.icon = db.Blob(icon)

        # new sort order ?
        scoreorder = self.request.get('scoreorder')
        if scoreorder:
            game.scoreorder = scoreorder

        # new homepage ?
        homepage = self.request.get('homepage')
        if homepage:
            game.homepage = homepage 

        # new app store URL ?
        appstore = self.request.get('appstore')
        if appstore:
            game.appstore = appstore

        # publish game in homepage
        publish = self.request.get('publish')
        if publish:
            bool_publish = publish == 'True'
            game.publish = bool_publish 

        game.put()

    # Update Display Web
    def update_displayweb( self, game ):
        fieldname = self.request.get('fieldname')
        if not fieldname:
            logging.error('EditGame: Fieldname not found')
            return

        displayweb = self.request.get('displayweb')
        if not displayweb:
            logging.error('EditGame: displayweb not found')
            return
        if displayweb == 'True':
            displayweb = True
        else:
            displayweb = False

        field = game.score_fields.filter('name =', fieldname).fetch(1)[0]
        field.displayweb = displayweb
        field.put()
        self.redirect('/user/edit-game?gamename=%s' % game.name)


    # Change the Score Type to int, string or float
#    def new_score_type( self, game ):
#        new_type = self.request.get("score_type")
#        field = game.score_fields.filter('name =','cc_score').fetch(1)[0]
#        field.delete()
#        field = ScoreField( key_name='cc_score', name='cc_score', type=new_type, admin=True, send=True, parent=game, game=game)
#        field.put()
#        
#        self.redirect('/user/edit-game?gamename=%s' % game.name)


    # puts a new field into the DB
    def new_field(self, game):
        # obtain field name
        fieldname = self.request.get('fieldname')
        if not fieldname:
            logging.error('Fieldname not found')
            return

        if not fieldname.startswith('usr_'):
            logging.error('Invalid fieldname')
            self.response.set_status(400)
            self.response.out.write('Invalid fieldname. It must start with "usr_"')
            return

        fieldtype = self.request.get('fieldtype')
        if not fieldtype:
            logging.error('Fieldtype not found')
            self.response.set_status(400)
            self.response.out.write('Missing fieldtype argument')
            return
        if not fieldtype in ('string','int','float'):
            logging.error('Invalid Fieldtype')
            self.response.set_status(400)
            self.response.out.write('Invalid field type. It must be one of these: string, int or float')
            return

        sendback = self.request.get('sendback')
        if not sendback:
            logging.error('Sendback not found')
            self.response.set_status(400)
            self.response.out.write('Missing sendback argument')
            return 
        if sendback == 'True':
            sendback = True
        else:
            sendback = False

        displayweb = self.request.get('displayweb')
        if not displayweb:
            logging.error('EditGame: displayweb not found')
            self.response.set_status(400)
            self.response.out.write('Missing displayweb argument')
            return 
        if displayweb == 'True':
            displayweb = True
        else:
            displayweb = False

        field = ScoreField( key_name=fieldname, name=fieldname, type=fieldtype, admin=False, send=sendback, displayweb=displayweb, parent=game, game=game)
        field.put()


#
# 'user/game/delete' handler
#
class DeleteGame(BaseHandler):

    @owner_of_game_required
    def post(self):
        # 'name' and 'game' already exists.
        # @owner_of_game_required is the predondition
        name = self.request.get('gamename')
        game = Game.get_by_key_name( name )

        # Delete scores that belongs to the game
        for s in game.scores:
            s.delete()

        # Delete scores by country statistics
        for sc in game.nro_scores_country:
            sc.delete()

        # Delete categories
        for c in game.categories:
            c.delete()

        # Delete fields
        for f in game.score_fields:
            f.delete()

        # Delete the game
        game.delete()
        self.redirect('/user/list-games')

#
# Delete all the scores from a given name
# and reset the count to 0
#
# 'user/delete-scores' handler
#
class DeleteScores(BaseHandler):

    @owner_of_game_required
    def post(self):

        # 'name' and 'game' already exists.
        # @owner_of_game_required is the predondition
        name = self.request.get('gamename')
        game = Game.get_by_key_name( name )

        if game.ranking_enabled:
            logging.error('DeleteScores: Cant delete scores when rankings are enabled')
            self.response.out.write('DeleteScores: Cant delete score when rankings are enabled')
            return

        for s in game.scores:
            s.delete()

        for sc in game.nro_scores_country:
            sc.delete()

        game.nro_scores = 0
        game.put()

        self.redirect('/user/list-games')
#
# 'user/delete-score' handler
#
class EditScores(BaseHandler):

    @owner_of_game_required
    def get(self):
        gamename = self.request.get("gamename")
        game = Game.get_by_key_name( gamename )

        offset = self.request.get("offset")
        if not offset:
            offset = 0
        else:
            offset = int(offset)
        query = game.scores

        category = self.request.get('category')
        if not category:
            # default category in case no category was specified
            if game.categories.count() > 0:
                category = game.categories[0].name
            else:
                category = ''

        country = self.request.get('country')
        if not country or country=='world':
            country = ''

        deviceid = self.request.get('deviceid')
        if not deviceid:
            deviceid = ''

        limit = 20

        order = '-cc_score'
        if game.scoreorder == 'asc':
            order = 'cc_score'
        # sort the scores by the score field
        query.ancestor( game )
        query.filter('cc_category =',category)
        query.order(order)
        if country:
            query.filter('cc_country =',country)
        if deviceid:
            query.filter('cc_device_id =',deviceid)
        scores = query.fetch(limit=limit, offset=offset)

        fields = game.score_fields

        show_prev = ( offset > 0 )
        show_next = ( len(scores) == limit )

        # iPhone ??
        supports_flash = not 'iphone' in os.environ['HTTP_USER_AGENT'].lower()

        params = {
            'offset' : offset,
            'next_offset' : offset + limit,
            'prev_offset' : offset - limit,
            'show_next' : show_next,
            'show_prev' : show_prev,
            'category' : category,
            'categories' : game.categories,
            'deviceid' : deviceid,
            'fields' : fields,
            'scores' : scores,
            'scores_by_country' : game.nro_scores_country,
            'total_countries' : game.nro_scores_country.count(),
            'game' : game,
            'dev' : game.owner,
            'country' : country,
            'supports_flash' : supports_flash,
            'page' : {'title' : 'Game Scores: %s (%s)' % (gamename,game.nro_scores,) },
        }
        self.respond('user-edit-scores', params)
    
    @owner_of_game_required
    def post(self):
        type = self.request.get("type")
        gamename = self.request.get('gamename')
        game = Game.get_by_key_name( gamename )
        if type=='delete_score':
            self.delete_score(game)
        else:
            logging.error('EditScores: Type not not found')
            self.response.out.write('EditScores: Type not found')
            return

        name = self.request.get("gamename")
        self.redirect('/user/edit-scores?gamename=%s' % name)

    def delete_score(self, game):
        '''delete one score from a game given the score key'''
        key = self.request.get("scorekey")
        if not key:
            logging.error('"scorekey" parameter not found')
            self.response.out.write('EditScores: "scorekey" parameter not found')
            return 

        # 'name' and 'game' already exists.
        # @owner_of_game_required is the predondition
        key = db.Key(key)
        score = Score.get( key )

        # scores country
        query = db.Query(ScoresCountry)
        query.ancestor( game )
        query.filter('country_code =', score.cc_country)
        score_country = query.fetch(limit=1)[0]

        if score:
            if game.ranking_enabled:
                #NOTE: this is the implementation to get profile ID in api.py
                profile_id = "%s@%s" % (score.cc_playername, score.cc_device_id)
                ranker = self.get_ranker( game.key(), score.cc_category )
                try:
                    ranker.SetScore( profile_id, None )
                except Exception, e:
                    logging.error('DeleteScore: cannot delete score from ranking')

            self.delete_score_transac( score, game, score_country ) #Delete score from DB after score is deleted from Ranker

        else:
            raise Exception('EditScores: Score not not found')

    # 
    # delete score, runs in trasaction
    #
    @transactional
    def delete_score_transac( self, score, game, score_country ):
        score.delete()
        score_country.quantity -= 1
        score_country.put()
        game.nro_scores -=1 
        game.put()
        #ranker.SetScore(name, None)

#
# Delete Category from Game
#
class DeleteCategory(BaseHandler):

    @owner_of_game_required
    def get(self):

        # get current user
        user = users.get_current_user()
        if not user:
            logging.error('DeleteCategory: User not not found')
            return

        # obtain developer id
        dev = Developer.get_by_key_name( user.email() )
        if not dev:
            logging.error('DeleteCategory: Developer not not found')
            return 

        # obtain game name
        gamename = self.request.get('gamename')
        if not gamename:
            logging.error('DeleteCategory: Gamename not not found')
            return

        # game belongs to developer ?
        game = dev.games.filter( 'name =', gamename ).fetch(limit = 1)[0]
        if not game:
            logging.error('DeleteCategory: Game not not found')
            return 

        # obtain category name
        catname = self.request.get('catname')
        if not catname:
            logging.error('DeleteCategory: catname not not found')
            return

        category = game.categories.filter('name =', catname).fetch( limit=1 )[0]
        category.delete()
        self.redirect('/user/edit-game?gamename=%s' % gamename)

#
# Delete Field from Game Fields
#
class DeleteField(BaseHandler):

    @owner_of_game_required
    def get(self):

        # get current user
        user = users.get_current_user()
        if not user:
            logging.error('User not not found')
            return

        # obtain developer id
        dev = Developer.get_by_key_name( user.email() )
        if not dev:
            logging.error('Developer not not found')
            return 

        # obtain game name
        gamename = self.request.get('gamename')
        if not gamename:
            logging.error('Gamename not not found')
            return

        # game belongs to developer ?
        game = dev.games.filter( 'name =', gamename ).fetch(limit = 1)[0]
        if not game:
            logging.error('Game not not found')
            return 

        # obtain field name
        fieldname = self.request.get('fieldname')
        if not fieldname:
            logging.error('Fieldname not not found')
            return

        field = game.score_fields.filter('name =', fieldname).fetch( limit=1 )[0]
        field.delete()
        self.redirect('/user/edit-game?gamename=%s' % gamename)


#
# returns the info related to the user
#
class UserInfo(BaseHandler):
    @login_required
    def get(self):
        user = users.get_current_user()
        if user:
            dev = Developer.get_by_key_name( user.email() )

            values = { 'dev' : dev }

            self.response.out.write( template.render('templates/user-info.html', values ) )
        else:
            self.response.out.write('you must be logged in')

#
# Logout
#
class Logout(BaseHandler):
    @login_required
    def get(self):
        self.login(None)
        self.redirect('/')



# GAE imports
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

webapp.template.register_template_library('django_hack')

application = webapp.WSGIApplication([
        ('/user/list-games', ListGames),
        ('/user/edit-scores', EditScores),
        ('/user/delete-scores', DeleteScores),
        ('/user/create-game', CreateGame),
        ('/user/delete-game', DeleteGame),
        ('/user/delete-field', DeleteField),
        ('/user/delete-category', DeleteCategory),
        ('/user/edit-game', EditGame),
        ('/user/edit-dev', EditDeveloper),
        ('/user/game-status', GameStatus),
        ('/user/user-info', UserInfo),
        ('/user/logout', Logout),
        ('/user/create-user', CreateUser),
        ],
        debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
