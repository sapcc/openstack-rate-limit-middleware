# Copyright 2019 SAP SE
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import unittest
import os
import json

from rate_limit import OpenStackRateLimitMiddleware
from . import fake


WORKDIR = os.path.dirname(os.path.realpath(__file__))
SWIFTCONFIGPATH = WORKDIR + '/fixtures/swift.yaml'


class TestOpenStackRateLimitMiddleware(unittest.TestCase):

    is_setup = False

    def setUp(self):
        if self.is_setup:
            return
        self.app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            wsgi_config={
                'config_file': SWIFTCONFIGPATH,
                'max_sleep_time_seconds': 15,
                'rate_buffer_seconds': 10,
                'clock_accuracy': '1ms',
            },
            memcached=fake.FakeMemcache()
        )
        self.is_setup = True

    def test_is_scope_whitelisted(self):
        self.assertTrue(
            self.app.is_scope_whitelisted("1233456789abcdef")
        )
        self.assertFalse(
            self.app.is_scope_whitelisted("abcdef")
        )

    def test_is_scope_blacklited(self):
        self.assertTrue(
            self.app.is_scope_blacklisted("abcdef1233456789")
        )
        self.assertFalse(
            self.app.is_scope_blacklisted("abcdef")
        )

    def test_ratelimit_response_from_config(self):
        self.assertEqual(
            self.app.ratelimit_response.status_code,
            498
        )
        self.assertEqual(
            self.app.ratelimit_response.headerlist,
            [('X-Foo', 'RateLimitFoo'), ('Content-Length', '19')]
        )
        # body is a bytes literal which is ignored by py2, but not py3
        self.assertEqual(
            str(self.app.ratelimit_response.body).lstrip("b'").rstrip("'"),
            'Rate Limit Exceeded'
        )

    def test_blacklist_response_from_config(self):
        self.assertEqual(
            self.app.blacklist_response.status_code,
            497
        )
        self.assertEqual(
            self.app.blacklist_response.headerlist,
            [('X-Foo', 'Bar'), ('Content-Length', '127')]
        )
        self.assertEqual(
            str(self.app.blacklist_response.json_body),
            json.dumps({"error": {"status": "497 Blacklisted", "message": "You have been blacklisted. Please contact and administrator."}})
        )

    def test_get_rate_limit(self):
        stimuli = [
            {
                'action': 'foo',
                'target_type_uri': 'bar',
                'expected': -1
            },
            {
                'action': 'create',
                'target_type_uri': 'account/container',
                'expected': '5r/30m'
            },
            {
                'action': 'read',
                'target_type_uri': 'account/container/object',
                'expected': '2r/m'
            }
        ]

        for stim in stimuli:
            action = stim.get('action')
            target_type_uri = stim.get('target_type_uri')
            expected_ratelimit = stim.get('expected')

            rate_limit = self.app.ratelimit_provider.get_global_rate_limits(action, target_type_uri)
            self.assertEqual(
                rate_limit,
                expected_ratelimit,
                "rate limit for '{0} {1}' should be '{2}' but got '{3}'".format(action, target_type_uri, expected_ratelimit, rate_limit)
            )


if __name__ == '__main__':
    unittest.main()
