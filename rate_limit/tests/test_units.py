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

from rate_limit.provider import BaseRateLimit, BucketRateLimit
from rate_limit.units import Units


class TestUnits(unittest.TestCase):

    def test_parse_sliding_window_rate_limit(self):
        stimuli = [
            {
                'input': BaseRateLimit(None, None, None, '5r/m'),
                'expected': (5.0, 60.0)
            },
            {
                'input': BaseRateLimit(None, None, None, '5r/s'),
                'expected': (5.0, 1.0)
            },
            {
                'input': BaseRateLimit(None, None, None, '5r/h'),
                'expected': (5.0, 3600.0)
            },
            {
                'input': BaseRateLimit(None, None, None, '100r/d'),
                'expected': (100.0, 24 * 3600.0)
            },
            {
                'input': BaseRateLimit(None, None, None, '5r/2m'),
                'expected': (5.0, 120.0)
            },
            {
                'input': BaseRateLimit(None, None, None, '5r/1m'),
                'expected': (5.0, 60.0)
            },
            {
                'input': BaseRateLimit(None, None, None, 'quark'),
                'expected': (-1.0, 1.0)
            },
            {
                'input': BaseRateLimit(None, None, None, '5r/1x'),
                'expected': (5.0, -1.0)
            },
            {
                'input': BaseRateLimit(None, None, None, '1rr/m'),
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

    def test_parse_sliding_window_rate_limit_buckets(self):
        bucket = BucketRateLimit(None, None, None, "10r/m", "random_bucket_name")
        expected = (10.0, 60.0)

        actual = Units.parse_sliding_window_rate_limit(bucket)

        self.assertEqual(
            actual,
            expected,
            "input was '{0}'. expected '{1}' but got '{2}'".format(input, expected, actual)
        )


if __name__ == '__main__':
    unittest.main()
