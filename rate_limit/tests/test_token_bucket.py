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

import json
import os
import random
import unittest
from unittest.mock import MagicMock

import eventlet

from rate_limit.backend import RedisBackend
from rate_limit.response import RateLimitExceededResponse
from rate_limit.units import Units


class TestParseTokenBucketRateLimit(unittest.TestCase):
    """Tests for Units.parse_token_bucket_rate_limit() parsing logic."""

    def test_basic_burst_syntax(self):
        result = Units.parse_token_bucket_rate_limit('100r/m,burst=3')
        self.assertIsNotNone(result)
        refill_rate, capacity = result
        self.assertAlmostEqual(refill_rate, 100.0 / 60.0, places=4)
        self.assertEqual(capacity, 3)

    def test_burst_per_second(self):
        result = Units.parse_token_bucket_rate_limit('10r/s,burst=5')
        self.assertIsNotNone(result)
        refill_rate, capacity = result
        self.assertAlmostEqual(refill_rate, 10.0, places=4)
        self.assertEqual(capacity, 5)

    def test_burst_per_hour(self):
        result = Units.parse_token_bucket_rate_limit('3600r/h,burst=10')
        self.assertIsNotNone(result)
        refill_rate, capacity = result
        self.assertAlmostEqual(refill_rate, 1.0, places=4)
        self.assertEqual(capacity, 10)

    def test_no_burst_returns_none(self):
        result = Units.parse_token_bucket_rate_limit('100r/m')
        self.assertIsNone(result)

    def test_plain_rate_returns_none(self):
        result = Units.parse_token_bucket_rate_limit('5r/s')
        self.assertIsNone(result)

    def test_invalid_rate_returns_none(self):
        result = Units.parse_token_bucket_rate_limit('quark,burst=3')
        self.assertIsNone(result)

    def test_invalid_burst_value_returns_none(self):
        result = Units.parse_token_bucket_rate_limit('100r/m,burst=abc')
        self.assertIsNone(result)

    def test_burst_with_multi_unit_window(self):
        result = Units.parse_token_bucket_rate_limit('10r/5m,burst=2')
        self.assertIsNotNone(result)
        refill_rate, capacity = result
        self.assertAlmostEqual(refill_rate, 10.0 / 300.0, places=4)
        self.assertEqual(capacity, 2)


class TestTokenBucketAlgorithm(unittest.TestCase):
    """Integration tests for the token bucket algorithm against a real Redis."""

    def setUp(self):
        self.configure_connection(max_sleep_time_seconds=600)

    def configure_connection(self, max_sleep_time_seconds):
        ratelimit_response = RateLimitExceededResponse(
            status="429", status_code=429, headerlist=[], body=None, json_body=None
        )
        host = os.getenv("REDIS_HOST", "localhost")
        port = os.getenv("REDIS_PORT", 6379)

        self.backend = RedisBackend(
            host=host,
            port=port,
            password=None,
            rate_limit_response=ratelimit_response,
            max_sleep_time_seconds=max_sleep_time_seconds,
            log_sleep_time_seconds=0,
        )

        if not self.backend.is_available()[0]:
            raise RuntimeError(f"Redis backend {host}:{port} is not available")

    def test_first_request_passes(self):
        """A new key should have a full bucket — first request always passes."""
        rand = random.randint(1, 100000)
        target_type = f"tb-first-{rand}"

        response = self.backend.rate_limit('local', "create", target_type, '100r/m,burst=3')
        self.assertIsNone(response, "Expected first request to pass (full bucket)")

    def test_burst_capacity_passes(self):
        """All requests within burst capacity should pass immediately."""
        rand = random.randint(1, 100000)
        target_type = f"tb-burst-{rand}"

        # burst=3 means 3 requests should pass immediately.
        for i in range(3):
            response = self.backend.rate_limit('local', "create", target_type, '100r/m,burst=3')
            self.assertIsNone(response, f"Expected request {i + 1} to pass (within burst capacity)")

    def test_burst_exhaustion_triggers_sleep(self):
        """4th request after burst=3 should trigger a sleep (not a 429)."""
        eventlet.sleep = MagicMock()
        rand = random.randint(1, 100000)
        target_type = f"tb-sleep-{rand}"

        # Exhaust the burst capacity.
        for i in range(3):
            self.backend.rate_limit('local', "create", target_type, '100r/m,burst=3')

        # 4th request should be suspended (not rejected) since max_sleep_time is large.
        response = self.backend.rate_limit('local', "create", target_type, '100r/m,burst=3')
        self.assertTrue(eventlet.sleep.called, "Expected eventlet.sleep to be called for suspended request")
        self.assertIsNone(response, "Expected suspended request to pass after sleep")

    def test_burst_exhaustion_triggers_429_when_sleep_disabled(self):
        """When max_sleep_time=0, burst exhaustion should return a 429."""
        self.configure_connection(max_sleep_time_seconds=0)
        rand = random.randint(1, 100000)
        target_type = f"tb-reject-{rand}"

        # Exhaust the burst capacity.
        for i in range(3):
            self.backend.rate_limit('local', "create", target_type, '100r/m,burst=3')

        # 4th request should be rejected with 429.
        response = self.backend.rate_limit('local', "create", target_type, '100r/m,burst=3')
        self.assertIsNotNone(response, "Expected response to be rate limited (429)")
        body = json.loads(response.json_body)
        self.assertEqual(body["error"]["message"], "Too Many Requests")

    def test_tokens_refill_after_wait(self):
        """After waiting long enough, tokens should refill and requests pass again."""
        rand = random.randint(1, 100000)
        target_type = f"tb-refill-{rand}"

        # Use a fast rate: 10r/s,burst=2 — refill 1 token every 0.1s.
        for i in range(2):
            self.backend.rate_limit('local', "create", target_type, '10r/s,burst=2')

        # Wait for refill (at least 0.1s for 1 token at 10r/s).
        eventlet.sleep(0.15)

        # Should pass again.
        response = self.backend.rate_limit('local', "create", target_type, '10r/s,burst=2')
        self.assertIsNone(response, "Expected request to pass after token refill")

    def test_mixed_sliding_window_and_token_bucket(self):
        """Sliding window configs still work alongside token bucket configs."""
        rand = random.randint(1, 100000)

        # Sliding window — should pass.
        target_type_sw = f"tb-mixed-sw-{rand}"
        response_sw = self.backend.rate_limit('local', "create", target_type_sw, '100r/m')
        self.assertIsNone(response_sw, "Expected sliding window request to pass")

        # Token bucket — should pass.
        target_type_tb = f"tb-mixed-tb-{rand}"
        response_tb = self.backend.rate_limit('local', "create", target_type_tb, '100r/m,burst=3')
        self.assertIsNone(response_tb, "Expected token bucket request to pass")


if __name__ == '__main__':
    unittest.main()
