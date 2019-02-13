import unittest
import fake
import os

from rate_limit import OpenStackRateLimitMiddleware

WORKDIR = os.path.dirname(os.path.realpath(__file__))
SWIFTCONFIGPATH = WORKDIR + '/fixtures/swift.yaml'
LIMESRATELIMITS = WORKDIR + '/fixtures/limes.json'
SERVICE_TYPE = 'object-store'


class TestOpenStackRateLimitMiddleware(unittest.TestCase):
    is_setup = False

    def setUp(self):
        if self.is_setup:
            return
        self.app = OpenStackRateLimitMiddleware(
            app=fake.FakeApp(),
            wsgi_config={
                'config_file': SWIFTCONFIGPATH,
                'max_sleep_time_seconds': 15,
                'rate_buffer_seconds': 10,
                'clock_accuracy': '1ms',
            }
        )
        self.is_setup = True

    def test(self):
        scope = '123456'
        action = 'read'
        target_type_uri = 'servers'

        response = self.app._rate_limit(scope=scope, action=action, target_type_uri=target_type_uri)