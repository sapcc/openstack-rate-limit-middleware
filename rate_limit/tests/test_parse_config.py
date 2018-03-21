# Copyright 2018 SAP SE
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

from rate_limit import common
from rate_limit.units import Units

WORKDIR = os.path.dirname(os.path.realpath(__file__))
SWIFTCONFIGPATH = WORKDIR + '/fixtures/swift.yaml'


class TestParseConfig(unittest.TestCase):
    def test_load_swift_config(self):
        conf = common.load_config(SWIFTCONFIGPATH)

        self.assertEqual(
            conf['blacklist'],
            ["abcdef1233456789", "abcdef1233456789abcdef", "abcdef1233456789"]
        )

        self.assertEqual(
            conf['whitelist'],
            ["1233456789abcdef", "1233456789abcdef1233456789"]
        )

        self.assertEqual(
            conf.get('rates').get('default'),
            {
                "account/container": [
                    {
                        "action": "update",
                        "limit": "2r/m"
                    },
                    {
                        "action": "create",
                        "limit": "5r/30m"
                    }
                ],
                "account/container/object": [
                    {
                        "action": "update",
                        "limit": "2r/m"
                    },
                    {
                        "action": "read",
                        "limit": "2r/m"
                    },
                ]
            }
        )

    def test_parse_and_convert_to_per_seconds(self):
        stimuli = [
            {
                'in':  '5r/s',
                'expected': 5
            },
            {
                'in': '1r/m',
                'expected': round(1/60.0, 4)
            },
            {
                'in': '10r/d',
                'expected': round(1/8640.0,4)
            },
            {
                'in': '0.5r/s',
                'expected': 1
            },
            {
                'in': '-1r/s',
                'expected': -1
            },
            {
                'in': '-5r/s',
                'expected': -1
            }
        ]

        for s in stimuli:
            input = s.get('in')
            expected = s.get('expected')
            actual = Units.parse_and_convert_to_per_seconds(input)

            self.assertEqual(
                actual,
                expected,
                "converting '{0}'. want: {1} but got: {2}".format(input, expected, actual)
            )

    def test_parse_and_convert_unit(self):
        self.assertEqual(0.1, Units.parse('100ms'))
        self.assertEqual(60, Units.parse('1m'))
        self.assertEqual(-1, Units.parse('mms'))


if __name__ == '__main__':
    unittest.main()
