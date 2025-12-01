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

import os
import unittest

from rate_limit.rate_limit import OpenStackRateLimitMiddleware

from rate_limit.tests import fake

WORKDIR = os.path.dirname(os.path.realpath(__file__))
CONFIGPATH = WORKDIR + '/fixtures/bucket.yaml'


class TestOpenStackRateLimitBuckets(unittest.TestCase):

    is_setup = False

    def setUp(self):
        if self.is_setup:
            return

        self.app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            config_file=CONFIGPATH,
            max_sleep_time_seconds=20
        )
        self.is_setup = True

    def test_get_bucket_based_local_rate_limit(self):
        stimuli = [
            {
                'action': 'update',
                'target_type_uri': 'routers/router/add_extraroutes',
                'expected': '2r/m'
            },
            {
                'action': 'update',
                'target_type_uri': 'routers/router/remove_extraroutes',
                'expected': "2r/m"
            },
            {
                'action': 'update',
                'target_type_uri': 'bucket/definition/missing',
                'expected': -1
            }
        ]
        scope = "fixedscope"

        for stim in stimuli:
            action = stim.get('action')
            target_type_uri = stim.get('target_type_uri')
            expected_ratelimit = stim.get('expected')

            rate_limit = self.app.ratelimit_provider.get_local_rate_limits(scope, action, target_type_uri)
            self.assertEqual(
                rate_limit,
                expected_ratelimit,
                "rate limit for '{0} {1}' should be '{2}' but got '{3}'".format(action, target_type_uri,
                                                                                expected_ratelimit, rate_limit)
            )

    def test_get_bucket_based_global_rate_limit(self):
        stimuli = [
            {
                'action': 'read',
                'target_type_uri': 'ports',
                'expected': '10r/m'
            },
            {
                'action': 'write',
                'target_type_uri': 'bucket/definition/missing',
                'expected': -1
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
                "rate limit for '{0} {1}' should be '{2}' but got '{3}'".format(action, target_type_uri,
                                                                                expected_ratelimit, rate_limit)
            )
