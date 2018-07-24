import unittest
import os
import json

from rate_limit import OpenStackRateLimitMiddleware
from rate_limit import limes
from . import fake


WORKDIR = os.path.dirname(os.path.realpath(__file__))
SWIFTCONFIGPATH = WORKDIR + '/fixtures/swift.yaml'
LIMESRATELIMITS = WORKDIR + '/fixtures/limes.json'


class TestOpenStackRateLimitMiddlewareWithLimes(unittest.TestCase):

    is_setup = False

    def setUp(self):
        if self.is_setup:
            return
        self.watcher = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            wsgi_config={
                'config_file': SWIFTCONFIGPATH,
                'max_sleep_time_seconds': 15,
                'rate_buffer_seconds': 10,
                'clock_accuracy': '1ms',
                'service_type': 'object-store'
            },
            memcached=fake.FakeMemcached()
        )
        lim = limes.Limes()
        lim.keystone = fake.FakeKeystoneclient()
        lim.limes_base_url = 'https://localhost:8887'

        # mock requests
        def _fake_get(path, params={}, headers={}):
            f = open(LIMESRATELIMITS)
            json_data = f.read()
            f.close()
            return json.loads(json_data)

        lim._get = _fake_get
        self.watcher.limes = lim

        self.is_setup = True

    def test_list_ratelimits_for_projects_in_domain(self):
        rate_limits = self.watcher.limes.list_ratelimits_for_projects_in_domain('fake_domain_id')
        self.assertIsNotNone(rate_limits)
        self.watcher.limes_rate_limits = rate_limits

        rate_limit, rate_strat = self.watcher.get_rate_limit_and_strategy_from_limes(
            'update', 'account/container/object', 'abcdef1233456789'
        )
        self.assertEqual(rate_limit, '10r/m', "the rate limit should be '10r/m'")
        self.assertEqual(rate_strat, 'fixedwindowstrategy', "the strategy should be 'fixedwindowstrategy'")

        rate_limit, rate_strat = self.watcher.get_rate_limit_and_strategy_from_limes(
            'delete', 'account/container', '1233456789abcdef1233456789'
        )
        self.assertEqual(rate_limit, '2r/10m', "the rate limit should be '2r/10m'")
        self.assertEqual(rate_strat, 'slidingwindowstrategy', "the strategy should be 'slidingwindowstrategy'")

        rate_limit, rate_strat = self.watcher.get_rate_limit_and_strategy_from_limes(
            'delete', 'account/container', 'non_existent_project_id'
        )
        self.assertIsNone(rate_limit, "the rate limit should be 'None'")
        self.assertIsNone(rate_strat, "the strategy should be 'None'")