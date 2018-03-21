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

from rate_limit.rate_limit import Units


class TestUnits(unittest.TestCase):

    def test_parse_sliding_window_rate_limit(self):
        stimuli = [
            {
                'input': '5r/m',
                'expected': (5.0, 60.0)
            },
            {
                'input': '5r/s',
                'expected': (5.0, 1.0)
            },
            {
                'input': '5r/h',
                'expected': (5.0, 3600.0)
            },
            {
                'input': '100r/d',
                'expected': (100.0, 24*3600.0)
            },
            {
                'input': '5r/2m',
                'expected': (5.0, 120.0)
            },
            {
                'input': '5r/1m',
                'expected': (5.0, 60.0)
            },
            {
                'input': 'quark',
                'expected': (-1.0, 1.0)
            },
            {
                'input': '5r/x',
                'expected': (5.0, -1.0)
            },
            {
                'input': '1rr/m',
                'expected': (-1.0, 1.0)
            }
        ]

        for stim in stimuli:
            input = stim.get('input')
            expected = stim.get('expected')
            actual = Units.parse_sliding_window_rate_limit(input)
            self.assertEqual(
                actual,
                expected,
                "input was '{0}'. expected '{1}' but got '{2}'".format(input, expected, actual)
            )


if __name__ == '__main__':
    unittest.main()
