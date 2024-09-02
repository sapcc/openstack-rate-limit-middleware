import copy
import unittest
import os
import json

from unittest.mock import patch

from rate_limit.ratelimit import provider

SERVICE_TYPE = 'object-store'



class TestOpenStackRateLimitMiddlewareWithLimes(unittest.TestCase):
    is_setup = False

    def setUp(self):
        self.dummy_conf = {
            'rates': {
                'default': [
                    {
                        'action': 'dummy/dummy',
                        'limit': '10r/m'
                    }
                ]
            }
        }
        rate_limit_provider = provider.ConfigurationRateLimitProvider(
            service_type=SERVICE_TYPE,
            refresh_interval_seconds=20
        )
        self.rate_limit_provider = rate_limit_provider
        self.rate_limit_provider.config = self.dummy_conf


    @patch('rate_limit.common.load_config')
    def test_update_rate_limits(self, mock_config):
        mock_config.return_value = self.dummy_conf
        self.assertEqual(self.rate_limit_provider.updated_rate_limit_config(), False,
                         "the rate limit should not be updated")

        new_conf = copy.deepcopy(self.dummy_conf)
        new_conf['rates']['default'][0]['limit'] = '20r/m'
        mock_config.return_value = new_conf
        self.assertEqual(self.rate_limit_provider.updated_rate_limit_config(), True,
                         "the rate limit should be updated")
