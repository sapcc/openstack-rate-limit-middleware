# Copyright 2024 SAP SE
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

import threading
import unittest
from unittest.mock import MagicMock, patch

import pyredis

from rate_limit import backend as rate_limit_backend
from rate_limit.response import RateLimitExceededResponse


def _make_backend(**kwargs):
    defaults = dict(
        host='127.0.0.1',
        port=6379,
        password=None,
        rate_limit_response=RateLimitExceededResponse(),
        max_sleep_time_seconds=20,
        log_sleep_time_seconds=1,
    )
    defaults.update(kwargs)
    return rate_limit_backend.RedisBackend(**defaults)


class TestRedisBackendPool(unittest.TestCase):

    def test_pool_is_none_before_reload(self):
        b = _make_backend()
        self.assertIsNone(b.pool)

    def test_reload_creates_pool(self):
        b = _make_backend()
        with patch('pyredis.Pool') as mock_cls:
            mock_cls.return_value = MagicMock()
            b.reload(password='secret')
        self.assertIsNotNone(b.pool)

    def test_reload_passes_username_to_pool_when_provided(self):
        b = _make_backend()
        with patch('pyredis.Pool') as mock_cls:
            mock_cls.return_value = MagicMock()
            b.reload(password='pass', username='alice')
        kwargs = mock_cls.call_args.kwargs
        self.assertEqual(kwargs['username'], 'alice')

    def test_reload_omits_username_from_pool_when_not_provided(self):
        b = _make_backend()
        with patch('pyredis.Pool') as mock_cls:
            mock_cls.return_value = MagicMock()
            b.reload(password='pass')
        kwargs = mock_cls.call_args.kwargs
        self.assertNotIn('username', kwargs)

    def test_reload_swaps_pool_atomically(self):
        b = _make_backend()
        with patch('pyredis.Pool') as mock_cls:
            first_pool = MagicMock()
            mock_cls.return_value = first_pool
            b.reload(password='pass1')
            second_pool = MagicMock()
            mock_cls.return_value = second_pool
            b.reload(password='pass2')
        self.assertIs(b.pool, second_pool)
        first_pool.close.assert_called_once()

    def test_reload_is_thread_safe(self):
        b = _make_backend()
        errors = []

        def do_reload(i):
            try:
                with patch('pyredis.Pool') as mock_cls:
                    mock_cls.return_value = MagicMock()
                    b.reload(password='pass{}'.format(i))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=do_reload, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])

    def test_reload_does_not_raise_when_pool_creation_fails(self):
        b = _make_backend()
        with patch('pyredis.Pool', side_effect=Exception('connection refused')):
            b.reload(password='pass')  # must not raise
        self.assertIsNone(b.pool)


class TestRedisBackendNonBlocking(unittest.TestCase):
    """Verify that a Redis error never causes rate_limit() to block or raise."""

    def _make_with_mock_pool(self, execute_side_effect=None, evalsha_side_effect=None):
        b = _make_backend()
        mock_pool = MagicMock()
        if execute_side_effect is not None:
            mock_pool.execute.side_effect = execute_side_effect
        if evalsha_side_effect is not None:
            mock_pool.evalsha.side_effect = evalsha_side_effect
            mock_pool.eval.side_effect = evalsha_side_effect
        with patch('pyredis.Pool', return_value=mock_pool):
            b.reload(password='pass')
        return b

    def test_rate_limit_returns_none_when_pool_not_initialized(self):
        b = _make_backend()
        # pool is None — no reload() called yet
        result = b.rate_limit(
            scope='proj-uuid',
            action='create',
            target_type_uri='compute/servers',
            max_rate_string='10r/m',
        )
        self.assertIsNone(result)

    def test_rate_limit_returns_none_when_redis_unreachable(self):
        b = self._make_with_mock_pool(
            execute_side_effect=pyredis.PyRedisError('connection refused'),
            evalsha_side_effect=pyredis.PyRedisError('connection refused'),
        )
        result = b.rate_limit(
            scope='proj-uuid',
            action='create',
            target_type_uri='compute/servers',
            max_rate_string='10r/m',
        )
        self.assertIsNone(result)

    def test_rate_limit_returns_none_when_redis_rejects_auth(self):
        b = self._make_with_mock_pool(
            execute_side_effect=pyredis.PyRedisError('WRONGPASS invalid username-password pair'),
            evalsha_side_effect=pyredis.PyRedisError('WRONGPASS invalid username-password pair'),
        )
        result = b.rate_limit(
            scope='proj-uuid',
            action='create',
            target_type_uri='compute/servers',
            max_rate_string='10r/m',
        )
        self.assertIsNone(result)

    def test_is_available_returns_false_when_pool_not_initialized(self):
        b = _make_backend()
        ok, msg = b.is_available()
        self.assertFalse(ok)

    def test_is_available_returns_false_when_redis_rejects_auth(self):
        b = self._make_with_mock_pool(
            execute_side_effect=pyredis.PyRedisError('WRONGPASS invalid username-password pair'),
        )
        ok, msg = b.is_available()
        self.assertFalse(ok)

    def test_is_available_returns_false_when_redis_unreachable(self):
        b = self._make_with_mock_pool(
            execute_side_effect=pyredis.PyRedisError('connection refused'),
        )
        ok, msg = b.is_available()
        self.assertFalse(ok)


if __name__ == '__main__':
    unittest.main()
