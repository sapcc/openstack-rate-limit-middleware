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
import time

from rate_limit import OpenStackRateLimitMiddleware
from rate_limit.response import RateLimitExceededResponse, BlacklistResponse
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
            }
        )
        self.is_setup = True

    def test_is_scope_whitelisted(self):
        self.assertTrue(
            self.app.is_scope_whitelisted("1233456789abcdef")
        )
        self.assertFalse(
            self.app.is_scope_whitelisted("abcdef")
        )

    def test_is_scope_blacklisted(self):
        self.assertTrue(
            self.app.is_scope_blacklisted("abcdef1233456789")
        )
        self.assertFalse(
            self.app.is_scope_blacklisted("abcdef")
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

    def test_is_ratelimited_swift_local_container_update(self):
        scope = '123456'
        action = 'update'
        target_type_uri = 'account/container'

        # The current configuration as per /fixtures/swift.yaml allows 2r/m for target type URI account/container and action update.
        # Thus the first 2 requests should not be rate limited but the 3rd one.
        expected = [
            # 1st requests not rate limited.
            None,
            # 2nd request also not rate limited.
            None,
            # 3rd request should be a rate limit response
            RateLimitExceededResponse(
                status='498 Rate Limited',
                body='Rate Limit Exceeded',
                headerlist=[('X-Retry-After', 58), ('X-RateLimit-Retry-After', 58),
                                        ('X-RateLimit-Limit', '2r/m'), ('X-RateLimit-Remaining', 0)]
            )
        ]

        for i in range(len(expected)):
            result = self.app._rate_limit(scope=scope, action=action, target_type_uri=target_type_uri)
            time.sleep(1)
            is_equal, msg = response_equal(expected[i], result)
            self.assertTrue(is_equal, msg)


def response_equal(expected, got):
    if isinstance(expected, (RateLimitExceededResponse, BlacklistResponse)) \
            and isinstance(got, (RateLimitExceededResponse, BlacklistResponse)):

        for h in expected.headerlist:
            if h not in got.headerlist:
                return False, "expected headers '{0}' but got '{1}'".format(expected.headerlist, got.headerlist)

        if expected.status != got.status:
            return False, "expected status '{0}' but got '{1}'".format(expected.status, got.status)

        if expected.has_body and expected.body != got.body:
                return False, "expected body '{0}' but got '{1}'".format(expected.body, got.body)

        if not expected.has_body and expected.json_body != got.json_body:
                return False, "expected json body '{0}' but got '{1}'".format(expected.json_body, got.json_body)

        return True, "items are equal"

    if type(expected) != type(got):
        return False, "expected type {0} but got type {1}".format(type(expected), type(got))

    # Compare arguments if neither RateLimitResponse nor BlacklistResponse.
    return expected == got, "expected '{0}' but got '{1}'".format(expected, got)


def headerlist_contains(headerlist, contains_tuple):
    b = contains_tuple in headerlist
    if not b:
        return False, "header '{0}' is missing in '{1}'".format(contains_tuple, headerlist)
    return True, ""


if __name__ == '__main__':
    unittest.main()
