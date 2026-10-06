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

import os
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch, call

from rate_limit import backend as rate_limit_backend
from rate_limit.rate_limit import OpenStackRateLimitMiddleware
from rate_limit.response import RateLimitExceededResponse
from . import fake

WORKDIR = os.path.dirname(os.path.realpath(__file__))
SWIFTCONFIGPATH = WORKDIR + '/fixtures/swift.yaml'


def _make_redis_backend(patcher, password='secret', username=None, host='127.0.0.1', port=6379):
    """Create a RedisBackend using an already-started pyredis.Pool patcher."""
    mock_pool_cls = patcher.start() if not hasattr(patcher, 'return_value') else patcher
    mock_pool_cls.return_value = MagicMock()
    response = RateLimitExceededResponse()
    b = rate_limit_backend.RedisBackend(
        host=host,
        port=port,
        password=password,
        username=username,
        rate_limit_response=response,
        max_sleep_time_seconds=20,
        log_sleep_time_seconds=1,
    )
    initial_pool = mock_pool_cls.return_value
    return b, mock_pool_cls, initial_pool


class TestRedisBackendUsername(unittest.TestCase):

    def setUp(self):
        self.patcher = patch('pyredis.Pool')
        self.mock_pool_cls = self.patcher.start()
        self.mock_pool_cls.return_value = MagicMock()

    def tearDown(self):
        self.patcher.stop()

    def _make(self, **kwargs):
        response = RateLimitExceededResponse()
        return rate_limit_backend.RedisBackend(
            host='127.0.0.1', port=6379,
            rate_limit_response=response,
            max_sleep_time_seconds=20,
            log_sleep_time_seconds=1,
            **kwargs,
        )

    def test_username_passed_to_pool_when_provided(self):
        self._make(password='secret', username='blue')

        kwargs = self.mock_pool_cls.call_args.kwargs
        self.assertEqual(kwargs['username'], 'blue')

    def test_username_not_passed_to_pool_when_omitted(self):
        self._make(password='secret')

        kwargs = self.mock_pool_cls.call_args.kwargs
        self.assertNotIn('username', kwargs)

    def test_password_always_passed_to_pool(self):
        self._make(password='mysecret')

        kwargs = self.mock_pool_cls.call_args.kwargs
        self.assertEqual(kwargs['password'], 'mysecret')


class TestRedisBackendReload(unittest.TestCase):

    def setUp(self):
        self.patcher = patch('pyredis.Pool')
        self.mock_pool_cls = self.patcher.start()
        self.mock_pool_cls.return_value = MagicMock()
        response = RateLimitExceededResponse()
        self.backend = rate_limit_backend.RedisBackend(
            host='127.0.0.1', port=6379,
            password='bluepass',
            username='blue',
            rate_limit_response=response,
            max_sleep_time_seconds=20,
            log_sleep_time_seconds=1,
        )
        self.initial_pool = self.mock_pool_cls.return_value
        self.mock_pool_cls.reset_mock()

    def tearDown(self):
        self.patcher.stop()

    def test_reload_creates_new_pool_with_new_credentials(self):
        new_pool = MagicMock()
        self.mock_pool_cls.return_value = new_pool

        self.backend.reload(username='green', password='greenpass')

        self.mock_pool_cls.assert_called_once()
        kwargs = self.mock_pool_cls.call_args.kwargs
        self.assertEqual(kwargs['username'], 'green')
        self.assertEqual(kwargs['password'], 'greenpass')

    def test_reload_without_username_omits_username_from_pool(self):
        self.mock_pool_cls.return_value = MagicMock()

        self.backend.reload(username=None, password='newpass')

        kwargs = self.mock_pool_cls.call_args.kwargs
        self.assertNotIn('username', kwargs)

    def test_reload_uses_new_pool_for_subsequent_requests(self):
        new_pool = MagicMock()
        new_pool.execute.return_value = b'redis_version:7.0.0\r\n'
        self.mock_pool_cls.return_value = new_pool

        self.backend.reload(username='green', password='greenpass')

        self.initial_pool.execute.reset_mock()
        self.backend.is_available()
        self.initial_pool.execute.assert_not_called()
        new_pool.execute.assert_called()

    def test_reload_is_thread_safe(self):
        errors = []

        def do_reload(i):
            try:
                self.mock_pool_cls.return_value = MagicMock()
                self.backend.reload(username=None, password=f'pass{i}')
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=do_reload, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])


class TestMiddlewareCredentialReload(unittest.TestCase):

    def _write_file(self, content):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False)
        f.write(content)
        f.close()
        return f.name

    def tearDown(self):
        for attr in ('_secret_file', '_username_file'):
            path = getattr(self, attr, None)
            if path and os.path.exists(path):
                os.unlink(path)

    def test_backend_username_read_from_file_at_startup(self):
        self._username_file = self._write_file('blue')
        self._secret_file = self._write_file('bluepass')

        app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            config_file=SWIFTCONFIGPATH,
            backend_secret_file=self._secret_file,
            backend_username_file=self._username_file,
            max_sleep_time_seconds=20,
        )

        self.assertEqual(app.backend_username, 'blue')

    def test_backend_password_and_username_passed_to_redis_backend(self):
        self._username_file = self._write_file('blue')
        self._secret_file = self._write_file('bluepass')

        with patch('pyredis.Pool') as mock_pool_cls:
            mock_pool_cls.return_value = MagicMock()
            app = OpenStackRateLimitMiddleware(
                app=fake.FakeApp(),
                config_file=SWIFTCONFIGPATH,
                backend='redis',
                backend_host='127.0.0.1',
                backend_secret_file=self._secret_file,
                backend_username_file=self._username_file,
                max_sleep_time_seconds=20,
            )

        kwargs = mock_pool_cls.call_args.kwargs
        self.assertEqual(kwargs['password'], 'bluepass')
        self.assertEqual(kwargs['username'], 'blue')

    def test_reload_credentials_reloads_password_from_file(self):
        self._secret_file = self._write_file('oldpass')

        app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            config_file=SWIFTCONFIGPATH,
            backend_secret_file=self._secret_file,
            max_sleep_time_seconds=20,
        )
        app.redis_backend = MagicMock()

        # Update the file with new password
        with open(self._secret_file, 'w') as f:
            f.write('newpass')

        app._reload_credentials()

        app.redis_backend.reload.assert_called_once_with(username=None, password='newpass')

    def test_reload_credentials_reloads_both_username_and_password(self):
        self._secret_file = self._write_file('oldpass')
        self._username_file = self._write_file('blue')

        app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            config_file=SWIFTCONFIGPATH,
            backend_secret_file=self._secret_file,
            backend_username_file=self._username_file,
            max_sleep_time_seconds=20,
        )
        app.redis_backend = MagicMock()

        with open(self._secret_file, 'w') as f:
            f.write('newpass')
        with open(self._username_file, 'w') as f:
            f.write('green')

        app._reload_credentials()

        app.redis_backend.reload.assert_called_once_with(username='green', password='newpass')

    def test_credential_watcher_started_when_secret_file_configured(self):
        self._secret_file = self._write_file('pass')
        before = threading.active_count()

        app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            config_file=SWIFTCONFIGPATH,
            backend_secret_file=self._secret_file,
            max_sleep_time_seconds=20,
        )

        self.assertGreater(threading.active_count(), before)

    def test_no_credential_watcher_without_secret_file(self):
        before = threading.active_count()

        OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            config_file=SWIFTCONFIGPATH,
            max_sleep_time_seconds=20,
        )

        self.assertEqual(threading.active_count(), before)

    def test_watcher_calls_reload_when_secret_file_changes(self):
        self._secret_file = self._write_file('oldpass')

        app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            config_file=SWIFTCONFIGPATH,
            backend_secret_file=self._secret_file,
            backend_secret_reload_interval=0.05,
            max_sleep_time_seconds=20,
        )
        app.redis_backend = MagicMock()

        time.sleep(0.1)
        with open(self._secret_file, 'w') as f:
            f.write('newpass')
        time.sleep(0.2)

        app.redis_backend.reload.assert_called_with(username=None, password='newpass')

    def test_missing_username_file_at_startup_does_not_crash(self):
        self._secret_file = self._write_file('pass')

        # Should not raise even though username file does not exist
        app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            config_file=SWIFTCONFIGPATH,
            backend_secret_file=self._secret_file,
            backend_username_file='/nonexistent/username.conf',
            max_sleep_time_seconds=20,
        )
        self.assertIsNone(app.backend_username)

    def test_missing_secret_file_at_startup_does_not_crash(self):
        # Should not raise even though secret file does not exist
        app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            config_file=SWIFTCONFIGPATH,
            backend_secret_file='/nonexistent/secret.conf',
            max_sleep_time_seconds=20,
        )
        self.assertIsNone(app.backend_password)

    def test_reload_credentials_skips_reload_when_secret_file_missing(self):
        self._secret_file = self._write_file('pass')

        app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            config_file=SWIFTCONFIGPATH,
            backend_secret_file='/nonexistent/secret.conf',
            max_sleep_time_seconds=20,
        )
        app.redis_backend = MagicMock()

        app._reload_credentials()

        app.redis_backend.reload.assert_not_called()

    def test_watcher_with_password_only_reloads_without_username(self):
        self._secret_file = self._write_file('oldpass')

        app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            config_file=SWIFTCONFIGPATH,
            backend_secret_file=self._secret_file,
            backend_secret_reload_interval=0.05,
            max_sleep_time_seconds=20,
        )
        app.redis_backend = MagicMock()

        time.sleep(0.1)
        with open(self._secret_file, 'w') as f:
            f.write('newpass')
        time.sleep(0.2)

        app.redis_backend.reload.assert_called_with(username=None, password='newpass')


if __name__ == '__main__':
    unittest.main()
