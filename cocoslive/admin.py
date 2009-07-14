#!/usr/bin/env python
#
# cocos live - (c) 2009 Ricardo Quesada
# http://www.cocoslive.net
#
# License: GNU GPL v3
# See the LICENSE file
#

#
# Everything related to the administration:
#   List Developers
#   List Games
#   etc..
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
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import login_required
from google.appengine.ext.webapp import template
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.api import images

# local imports
from model import Developer, Game, Score, ScoreField, Category, DefaultValues
from util import *
import configuration

def admin_required(func):
    """Ensure that the logged in user is an administrator."""

    @functools.wraps(func)
    def __wrapper(self, *args, **kwds):
        """Makes it possible for admin_required to be used as a decorator."""
        user = users.get_current_user()
        if not user:
            logging.error('Fobidden: must be logged in')
            return self.forbidden('You must be logged in')

        if users.is_current_user_admin():
            return func(self, *args, **kwds)  # pylint: disable-msg=W0142
        else:
            logging.error('Fobidden: must have admin privileges')
            return self.forbidden('You must have admin privileges')

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

#
# '/admin/' handler
#
class AdminHandler(BaseHandler):
    @admin_required
    def get(self):
        params = {
            'page' : {'title' : 'Admin'},
        }
        self.respond('admin', params)

# 
#
# '/admin/list-games-ready' handler
#
class ListGamesReady(BaseHandler):

    @admin_required
    def get(self):
        games = Game.all().filter('publish =',True)

        params = {
            'games' : games,
            'page' : {'title' : 'Games'},
        }
        self.respond('admin-games-ready', params)


    @admin_required
    def post(self):
        '''HTTP POST handler'''


        # obtain game name
        gamename = self.request.get('gamename')
        if not gamename:
            logging.error('Gamename not found')
            return

        # game belongs to developer ?
        game = Game.all().filter( 'name =', gamename ).fetch(limit = 1)[0]
        if not game:
            logging.error('Game not found')
            return 

        # type of POST
        type = self.request.get('type')
        if type == 'update_publish':
            self.update_publish( game )
        else:
            logging.error('Type not found')
            self.error(404)

        self.redirect('/admin/list-games-ready' )


    # Updates the "publish" property
    def update_publish( self, game ):
        # new category to game
        new_value = self.request.get('publish_value')
        if not new_value:
            logging.error('ListDevelopers: POST: missing publish_value')
            return

        new_value = (new_value == 'True')

        game.publish = new_value
        game.put()
# 
#
# '/admin/list-games' handler
#
class ListGames(BaseHandler):

    @admin_required
    def get(self):
        games = Game.all().order('-creationdate')

        params = {
            'games' : games,
            'page' : {'title' : 'Games'},
        }
        self.respond('admin-games', params)


    @admin_required
    def post(self):
        '''HTTP POST handler'''


        # obtain game name
        gamename = self.request.get('gamename')
        if not gamename:
            logging.error('Gamename not found')
            return

        # game belongs to developer ?
        game = Game.all().filter( 'name =', gamename ).fetch(limit = 1)[0]
        if not game:
            logging.error('Game not found')
            return 

        # type of POST
        type = self.request.get('type')
        if type == 'update_publish':
            self.update_publish( game )
        else:
            logging.error('Type not found')
            self.error(404)

        self.redirect('/admin/list-games' )


    # Updates the "publish" property
    def update_publish( self, game ):
        # new category to game
        new_value = self.request.get('publish_value')
        if not new_value:
            logging.error('ListDevelopers: POST: missing publish_value')
            return

        new_value = (new_value == 'True')

        game.publish = new_value
        game.put()
# 
#
# '/admin/list-devs' handler
#
class ListDevelopers(BaseHandler):

    @admin_required
    def get(self):
        devs = Developer.all().order('-creationdate')

        params = {
            'devs' : devs,
            'page' : {'title' : 'Developers'},
        }
        self.respond('admin-devs', params)


 
#
# '/admin/list-devs-updates' handler
#
class ListDevelopersUpdates(BaseHandler):

    @admin_required
    def get(self):
        devs = Developer.all().order('-creationdate').filter('receive_updates =', True)

        params = {
            'devs' : devs,
            'page' : {'title' : 'Developers with Updates'},
        }
        self.respond('admin-devs-updates', params)

#
# '/admin/default-values' handler
#
class Defaults(BaseHandler):

    @admin_required
    def get(self):
        defaults = DefaultValues.get_by_key_name('default')

        params = {
            'default_values' : defaults,
            'page' : {'title' : 'Default Values'},
        }
        self.respond('admin-defaults', params)


    @admin_required
    def post(self):
        '''HTTP POST handler'''

        # type of POST
        type = self.request.get('type')
        if type == 'update_defaults':
            self.update_defaults()
        else:
            logging.error('Type not found')
            self.error(404)

        self.redirect('/admin/default-values' )


    def get_or_create_defaults( self ):
        defaults = DefaultValues.get_by_key_name('default')
        if not defaults:
            defaults = DefaultValues( key_name = 'default' )
        return defaults

    # update default values
    def update_defaults( self ):

        defaults = self.get_or_create_defaults()

        # new game icon?
        game_icon = self.request.get("game_icon")
        if game_icon:
            game_icon = images.resize( game_icon,57,57)
            defaults.game_icon = db.Blob(game_icon)

        # new dev icon ?
        dev_icon = self.request.get("dev_icon")
        if dev_icon:
            dev_icon = images.resize( dev_icon,57,57)
            defaults.dev_icon = db.Blob(dev_icon)

        defaults.put()

# GAE imports
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app


application = webapp.WSGIApplication([
        ('/admin/list-devs', ListDevelopers),
        ('/admin/list-games', ListGames),
        ('/admin/list-games-ready', ListGamesReady),
        ('/admin/default-values', Defaults),
        ('/admin/list-devs-updates', ListDevelopersUpdates),
        ('/admin/', AdminHandler),
        ],
        debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
