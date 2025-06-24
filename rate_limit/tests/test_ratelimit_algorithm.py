import eventlet
import json
import os
import random
import unittest

from rate_limit.backend import RedisBackend
from rate_limit.response import RateLimitExceededResponse
from unittest.mock import MagicMock


class TestRateLimitAlgorithm(unittest.TestCase):
    def setUp(self):
        self.configure_connection(max_sleep_time_seconds=600)

    def configure_connection(self, max_sleep_time_seconds):
        ratelimit_response = RateLimitExceededResponse(
            status="429", status_code=429, headerlist=[], body=None, json_body=None
        )
        host = os.getenv("REDIS_HOST", "localhost")
        port = os.getenv("REDIS_PORT", 6379)

        self.backend = RedisBackend(host=host,
                                    port=port,
                                    password=None,
                                    rate_limit_response=ratelimit_response,
                                    max_sleep_time_seconds=max_sleep_time_seconds,
                                    log_sleep_time_seconds=0, )

        if not self.backend.is_available()[0]:
            raise RuntimeError(f"Redis backend {host}:{port} is not available")

    def test_rate_limit_hit(self):
        rand = random.randint(1, 1000)
        target_type = f"port-x{str(rand)}"

        response = self.backend.rate_limit('local', "create", target_type, '100r/m', )
        self.assertIsNone(response, "Expected response not to be limited")

    def test_rate_limit_hit_not_suspension(self):
        eventlet.sleep = MagicMock()
        rand = random.randint(1, 1000)
        target_type = f"port-y{str(rand)}"

        # First request should not hit the rate limit
        resp1 = self.backend.rate_limit('local', "suspend", target_type, '1r/m', )
        resp2 = self.backend.rate_limit('local', "suspend", target_type, '1r/m', )

        self.assertEqual(True, eventlet.sleep.called)
        self.assertIsNone(resp1, "Expected response not to be limited")
        self.assertIsNone(resp2, "Expected response not to be limited")

    def test_rate_limit_hit_not_suspended(self):
        self.configure_connection(max_sleep_time_seconds=0)
        rand = random.randint(1, 1000)
        target_type = f"port-z{str(rand)}"

        # First request should not hit the rate limit
        resp1 = self.backend.rate_limit('local', "suspend", target_type, '1r/m', )
        resp2 = self.backend.rate_limit('local', "suspend", target_type, '1r/m', )

        if not resp2:
            self.assertIsNotNone(resp2, "Expected response to be rate limited")

        body = json.loads(resp2.json_body)
        self.assertIsNone(resp1, "Expected response not to be limited")
        self.assertEqual(body["error"]["message"], "Too Many Requests")
