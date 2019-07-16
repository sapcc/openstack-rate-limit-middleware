import unittest
import os
import json

from rate_limit import OpenStackRateLimitMiddleware
from rate_limit import provider
from rate_limit import limes_types
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
            f = open(LIMESRATELIMITS).read()
            rl = limes_types.decode_limes_json(str(f))
            return rl

        limes_provider._get = _fake_get
        self.app.ratelimit_provider = limes_provider

        self.is_setup = True

    def test_parse_limes_json(self):
        f = open(LIMESRATELIMITS).read()
        project_rate_limits = limes_types.decode_limes_json(str(f))
        self.assertIsNotNone(project_rate_limits)

        stimuli = [
            {
                'project_id': '1233456789abcdef1233456789',
                'target_type_uri': 'account/container/object',
                'action': 'create',
                'expected': '10r/s'
            },
            {
                'project_id': '1233456789abcdef1233456789',
                'target_type_uri': 'account/container/object',
                'action': 'notExistent',
                'expected': None
            }
        ]

        for s in stimuli:
            project_id = s.get('project_id', None)
            target_type_uri = s.get('target_type_uri', None)
            action = s.get('action', None)
            expected = s.get('expected', None)

            got = project_rate_limits.get_rate_limit(
                project_id=project_id,
                service_type='object-store',
                target_type_uri=target_type_uri,
                action=action
            )

            self.assertEqual(
                got, expected,
                "the rate limit for '{0} {1}' should be '{2}' but got '{3}'".format(action, target_type_uri, expected, got)
            )

    def test_to_key_rate_limit_dict(self):
        f = open(LIMESRATELIMITS).read()
        project_rate_limits = limes_types.decode_limes_json(str(f))
        self.assertIsNotNone(project_rate_limits)

        got_rate_limit_key_dict = project_rate_limits.to_key_rate_limit_dict()
        expected_dict_subset = {'limes_ratelimit_1233456789abcdef1233456789_create_account/container/object': '10r/s'}

        self.assertDictContainsSubset(
            expected_dict_subset,
            got_rate_limit_key_dict,
            "{0} should contain {1} but doesn't".format(got_rate_limit_key_dict, expected_dict_subset)
        )

    def test_list_ratelimits_for_projects_in_domain(self):
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
