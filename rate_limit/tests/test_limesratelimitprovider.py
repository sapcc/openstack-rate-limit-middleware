import unittest
import os
import json

from rate_limit.rate_limit import OpenStackRateLimitMiddleware, provider
from . import fake

WORKDIR = os.path.dirname(os.path.realpath(__file__))
SWIFTCONFIGPATH = WORKDIR + '/fixtures/swift.yaml'
LIMESRATELIMITS = WORKDIR + '/fixtures/limes.json'
SERVICE_TYPE = 'object-store'


class TestOpenStackRateLimitMiddlewareWithLimes(unittest.TestCase):

    is_setup = False

    def setUp(self):
        if self.is_setup:
            return

        self.app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            config_file=SWIFTCONFIGPATH,
            max_sleep_time_seconds=15,
            service_type=SERVICE_TYPE
        )

        limes_provider = provider.LimesRateLimitProvider(
            service_type=SERVICE_TYPE,
            refresh_interval_seconds=20,
            keystone_client=fake.FakeKeystoneclient(),
            limes_api_url='https://localhost:8887'
        )

        # Mock requests to Limes.
        def _fake_get(path, params={}, headers={}):
            f = open(LIMESRATELIMITS)
            json_data = f.read()
            f.close()
            return json.loads(json_data)

        limes_provider._get = _fake_get
        self.app.ratelimit_provider = limes_provider

        self.is_setup = True

    def test_list_ratelimits_for_projects_in_domain(self):
        rate_limits = self.app.ratelimit_provider.list_ratelimits_for_projects_in_domain('fake_domain_id')
        self.assertIsNotNone(rate_limits)
        self.app.ratelimit_provider.rate_limits = rate_limits

        rate_limit = self.app.ratelimit_provider.get_local_rate_limits(
            'abcdef1233456789', 'update', 'account/container/object'
        )
        self.assertEqual(rate_limit, '10r/m', "the rate limit should be '10r/m' but got '{0}'".format(rate_limit))

        rate_limit = self.app.ratelimit_provider.get_local_rate_limits(
            '1233456789abcdef1233456789', 'delete', 'account/container'
        )
        self.assertEqual(rate_limit, '2r/10m', "the rate limit should be '2r/10m' but got '{0}'".format(rate_limit))

        rate_limit = self.app.ratelimit_provider.get_local_rate_limits(
            'non_existent_project_id', 'delete', 'account/container'
        )
        self.assertEqual(rate_limit, -1, "the rate limit should be '-1' but got '{0}'".format(rate_limit))
