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

from rate_limit import OpenStackRateLimitMiddleware

from . import fake


WORKDIR = os.path.dirname(os.path.realpath(__file__))
CONFIGPATH = WORKDIR + '/fixtures/groups.yaml'


class TestActionGroups(unittest.TestCase):

    is_setup = False

    def setUp(self):
        if self.is_setup:
            return
        self.app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            wsgi_config={
                'config_file': CONFIGPATH
            }
        )
        self.is_setup = True

    def test_groups(self):
        rl_groups = self.app.rate_limit_groups
        self.assertIsNotNone(
            rl_groups,
            "expected rate limit groups to be '{0}' but got '{1}'".format(
"""
groups:
  write:
    - update
    - delete

  read:
    - read
    - read/list
""",
                rl_groups
            )
        )

    def test_mapping(self):
        rl_groups = self.app.rate_limit_groups

        stimuli = [
            {
                'action': 'create',
                'expected': 'create'
            },
            {
                'action': 'update',
                'expected': 'write'
            },
            {
                'action': 'delete',
                'expected': 'write'
            },
            {
                'action': 'read',
                'expected': 'read'
            },
            {
                'action': 'read/list',
                'expected': 'read'
            },
        ]

        for stim in stimuli:
            action = stim.get('action')
            expected_action = stim.get('expected')

            got_action = self.app.get_action_from_rate_limit_groups(action)
            self.assertEqual(
                got_action,
                expected_action,
                "action should be '{0}' but got '{1}'".format(expected_action, got_action)
            )


if __name__ == '__main__':
    unittest.main()