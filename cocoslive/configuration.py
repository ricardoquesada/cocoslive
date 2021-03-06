#!/usr/bin/python2.5
#
# Copyright 2008 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""System-wide configuration variables."""

import datetime


# This HTML block will be printed in the footer of every page.
FOOTER_HTML = (
    'cocos Live v0.3.6 - &copy; 2009 <a href="http://www.sapusmedia.com">Sapus Media</a>'
    )


# File caching controls
FILE_CACHE_CONTROL = 'private, max-age=86400'
FILE_CACHE_TIME = datetime.timedelta(days=1)


# Title for the website
SYSTEM_TITLE = 'cocos Live'


# Unique identifier from Google Analytics
ANALYTICS_ID = 'UA-871936-6'
