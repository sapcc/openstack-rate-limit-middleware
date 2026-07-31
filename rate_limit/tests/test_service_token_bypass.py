# Copyright 2026 SAP SE
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

from . import fake

WORKDIR = os.path.dirname(os.path.realpath(__file__))
SWIFTCONFIGPATH = WORKDIR + '/fixtures/swift.yaml'


class TestServiceTokenBypassHelper(unittest.TestCase):
    """Tests for `_has_valid_service_token` — pure header inspection."""

    @classmethod
    def setUpClass(cls):
        cls.app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            config_file=SWIFTCONFIGPATH,
            max_sleep_time_seconds=20,
            bypass_service_token=True,
        )

    def test_valid_service_token_returns_true(self):
        environ = {
            'HTTP_X_SERVICE_TOKEN': 'gAAAAABabc...',
            'HTTP_X_SERVICE_IDENTITY_STATUS': 'Confirmed',
        }
        self.assertTrue(self.app._has_valid_service_token(environ))

    def test_missing_token_returns_false(self):
        environ = {
            'HTTP_X_SERVICE_IDENTITY_STATUS': 'Confirmed',
        }
        self.assertFalse(self.app._has_valid_service_token(environ))

    def test_token_present_but_status_not_confirmed(self):
        environ = {
            'HTTP_X_SERVICE_TOKEN': 'gAAAAABabc...',
            'HTTP_X_SERVICE_IDENTITY_STATUS': 'Invalid',
        }
        self.assertFalse(self.app._has_valid_service_token(environ))

    def test_token_present_status_missing(self):
        environ = {
            'HTTP_X_SERVICE_TOKEN': 'gAAAAABabc...',
        }
        self.assertFalse(self.app._has_valid_service_token(environ))

    def test_empty_token_string(self):
        environ = {
            'HTTP_X_SERVICE_TOKEN': '',
            'HTTP_X_SERVICE_IDENTITY_STATUS': 'Confirmed',
        }
        self.assertFalse(self.app._has_valid_service_token(environ))

    def test_empty_environ(self):
        self.assertFalse(self.app._has_valid_service_token({}))

    def test_none_environ(self):
        self.assertFalse(self.app._has_valid_service_token(None))

    def test_status_case_sensitive(self):
        # Match `internal-only-middleware` exactly: only the literal
        # string "Confirmed" counts.
        environ = {
            'HTTP_X_SERVICE_TOKEN': 'gAAAAABabc...',
            'HTTP_X_SERVICE_IDENTITY_STATUS': 'confirmed',
        }
        self.assertFalse(self.app._has_valid_service_token(environ))


class TestServiceTokenBypassIntegration(unittest.TestCase):
    """Tests for the `_rate_limit()` short-circuit."""

    def _new_app(self, **extra_conf):
        return OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            config_file=SWIFTCONFIGPATH,
            max_sleep_time_seconds=20,
            **extra_conf,
        )

    def test_bypass_disabled_by_default(self):
        app = self._new_app()
        self.assertFalse(app.bypass_service_token)

    def test_bypass_enabled_via_string_true(self):
        # paste.ini delivers values as strings.
        app = self._new_app(bypass_service_token='true')
        self.assertTrue(app.bypass_service_token)

    def test_bypass_enabled_via_native_true(self):
        app = self._new_app(bypass_service_token=True)
        self.assertTrue(app.bypass_service_token)

    def test_bypass_disabled_via_string_false(self):
        app = self._new_app(bypass_service_token='false')
        self.assertFalse(app.bypass_service_token)

    def test_rate_limit_bypassed_when_enabled_and_token_valid(self):
        app = self._new_app(bypass_service_token=True)
        environ = {
            'HTTP_X_SERVICE_TOKEN': 'gAAAAABabc...',
            'HTTP_X_SERVICE_IDENTITY_STATUS': 'Confirmed',
        }
        # Use a scope/action/target combination that WOULD be rate limited
        # without the bypass (account/container update — 2r/m in swift.yaml).
        # Fire enough requests that without the bypass we would see a
        # rate-limit response on at least one of them.
        scope = '123456'
        action = 'update'
        target_type_uri = 'account/container/foo_object'

        for _ in range(5):
            result = app._rate_limit(
                scope=scope, action=action, target_type_uri=target_type_uri,
                environ=environ,
            )
            self.assertIsNone(
                result,
                "expected None (bypass) but got rate-limit response: {0}".format(result)
            )

    def test_rate_limit_not_bypassed_when_flag_disabled(self):
        # Flag off → the headers are ignored, normal rate limiting kicks in.
        app = self._new_app(bypass_service_token=False)
        environ = {
            'HTTP_X_SERVICE_TOKEN': 'gAAAAABabc...',
            'HTTP_X_SERVICE_IDENTITY_STATUS': 'Confirmed',
        }
        # Whitelisted scope from swift.yaml → still returns None, but via
        # the existing whitelist code path, not the new bypass. Use a
        # non-whitelisted scope to actually exercise the rate limiter.
        scope = 'non-whitelisted-project'
        action = 'update'
        target_type_uri = 'account/container/foo_object'

        # First few requests pass; eventually rate limited.
        results = []
        for _ in range(5):
            results.append(app._rate_limit(
                scope=scope, action=action, target_type_uri=target_type_uri,
                environ=environ,
            ))
        # Without the bypass and at this rate (2r/m), at least one of these
        # 5 fast requests must be rate limited.
        self.assertTrue(
            any(r is not None for r in results),
            "expected at least one rate-limit response when bypass is off, got: {0}".format(results)
        )

    def test_rate_limit_not_bypassed_when_token_invalid(self):
        # Flag on but the status header says the token was rejected.
        app = self._new_app(bypass_service_token=True)
        environ = {
            'HTTP_X_SERVICE_TOKEN': 'gAAAAABabc...',
            'HTTP_X_SERVICE_IDENTITY_STATUS': 'Invalid',
        }
        scope = 'non-whitelisted-project-2'
        action = 'update'
        target_type_uri = 'account/container/foo_object'

        results = []
        for _ in range(5):
            results.append(app._rate_limit(
                scope=scope, action=action, target_type_uri=target_type_uri,
                environ=environ,
            ))
        self.assertTrue(
            any(r is not None for r in results),
            "expected at least one rate-limit response when token is invalid, got: {0}".format(results)
        )

    def test_rate_limit_not_bypassed_when_no_environ_passed(self):
        # Callers that pre-date the new environ kwarg keep working.
        app = self._new_app(bypass_service_token=True)
        scope = 'non-whitelisted-project-3'
        action = 'update'
        target_type_uri = 'account/container/foo_object'

        # No environ → no bypass → normal rate limiting.
        results = []
        for _ in range(5):
            results.append(app._rate_limit(
                scope=scope, action=action, target_type_uri=target_type_uri,
            ))
        self.assertTrue(
            any(r is not None for r in results),
            "expected at least one rate-limit response when environ is absent, got: {0}".format(results)
        )


if __name__ == '__main__':
    unittest.main()
