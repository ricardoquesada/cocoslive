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
import random
import logging
import functools

# GAE imports
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp.util import login_required
from google.appengine.ext.webapp import template
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.api import images
from google.appengine.api import datastore
from google.appengine.api import datastore_errors
from google.appengine.api import datastore_types

# local imports
from model import *
from util import *
import configuration
from ranker import ranker


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
# '/' handler
#
class MainPage(BaseHandler):

    def get(self):
        '''show 5 random games that are in the "publish" state'''

        user = users.get_current_user()

        query_str = "SELECT * FROM Game WHERE publish=True"
        games = db.GqlQuery (query_str)

        selected_games = []
        selected_idx = []

        total = games.count()
        max_number = min( total, 5 )

        while len(selected_games) < max_number:
            idx = random.randrange(0,total)
            if not idx in selected_idx:
                selected_idx.append( idx )
                selected_games.append( games[idx] )

        params = {
            'games' : selected_games,
            'user' : user,
            'page' : {'title' : 'Welcome'},
        }
        self.respond('main', params)


class GameScores(BaseHandler):

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

        if game.ranking_enabled:
            self.game = game        # needed for get_or_create_ranker
            ranker = self.get_or_create_ranker( game.key(), category )
            s = map( lambda y: [y.cc_score], scores)
            ranks = ranker.FindRanks( s )
            for i,item in enumerate(scores):
                item.position = ranks[i]+1
        else:
            for i,item in enumerate(scores):
                item.position = offset + i + 1

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
        self.respond('game-scores', params)

#
# Icon Handler
#
class GameIconHandler(BaseHandler):
    def get(self):

        # icon for game ?
        gamename = self.request.get("gamename")
        if gamename:
            game = Game.get_by_key_name( gamename )
            if game and game.icon:
                self.response.headers['Content-Type'] = "image/png"
                self.response.out.write(game.icon)
            else:
                defaults = DefaultValues.get_by_key_name( 'default' )
                self.response.headers['Content-Type'] = "image/png"
                self.response.out.write(defaults.game_icon)
        else:
            self.response.out.write("No image")
#
# Dev Icon Handler
#
class DevIconHandler(BaseHandler):
    def get(self):

        # icon for game ?
        devname = self.request.get("devname")
        if devname:
            dev = Developer.get_by_key_name( devname)
            if dev and dev.icon:
                self.response.headers['Content-Type'] = "image/png"
                self.response.out.write(dev.icon)
            else:
                defaults = DefaultValues.get_by_key_name( 'default' )
                self.response.headers['Content-Type'] = "image/png"
                self.response.out.write(defaults.dev_icon)
        else:
            self.response.out.write("No image")

#
# Default Icon Handler
#
class DefaultIconHandler(BaseHandler):
    def get(self):
        icontype = self.request.get("icontype")
        if icontype:
            defaults = DefaultValues.get_by_key_name( 'default' )
            if icontype == 'dev':
                self.response.headers['Content-Type'] = "image/png"
                self.response.out.write(defaults.dev_icon)
            elif icontype == 'game':
                self.response.headers['Content-Type'] = "image/png"
                self.response.out.write(defaults.game_icon)
            else:
                self.response.out.write("No image")
        else:
            self.response.out.write("No image")
#

#
# '/news' handler
#
class ListNews(BaseHandler):

    def get(self):
        params = {
            'page' : {'title' : 'Latest News'},
        }
        self.respond('news', params)

#
# '/games' handler
#
class GamesUsingCocosLive(BaseHandler):

    def get(self):

        query_str = "SELECT * FROM Game WHERE publish=True"
#        query_str = "SELECT * FROM Game"
        games = db.GqlQuery(query_str)

        params = {
            'games' : games,
            'page' : {'title' : 'Games Using Cocos Live'},
        }
        self.respond('games', params)
        
#
# '/tools' handler
#
class ToolsInfo(BaseHandler):

    def get(self):
        params = {
            'page' : {'title' : 'Developer Tools'},
        }
        self.respond('tools', params)

#
# '/about' handler
#
class AboutThisService(BaseHandler):

    def get(self):
        params = {
            'page' : {'title' : 'About Cocos Live'},
        }
        self.respond('about', params)

#
# '/help' handler
#
class HelpTopics(BaseHandler):

    def get(self):
        params = {
            'page' : {'title' : 'Help'},
        }
        self.respond('help', params)

#
# '/faq' handler
#
class FrequentlyAskedQuestions(BaseHandler):

    def get(self):
        params = {
            'page' : {'title' : 'Frequently Asked Questions'},
        }
        self.respond('faq', params)



#
# Dispatcher
#

webapp.template.register_template_library('django_hack')

application = webapp.WSGIApplication(
        [('/', MainPage),
        ('/game-scores', GameScores),
        ('/icon/game', GameIconHandler),
        ('/icon/dev', DevIconHandler),
        ('/icon/default', DefaultIconHandler),
        ('/news', ListNews),
        ('/games', GamesUsingCocosLive),
        ('/tools', ToolsInfo),
        ('/about', AboutThisService),
        ('/help', HelpTopics),
        ('/faq', FrequentlyAskedQuestions),
        ],
        debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
