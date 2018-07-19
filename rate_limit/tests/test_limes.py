import unittest
import os
import json

from rate_limit import OpenStackRateLimitMiddleware
from . import fake


WORKDIR = os.path.dirname(os.path.realpath(__file__))
SWIFTCONFIGPATH = WORKDIR + '/fixtures/swift.yaml'


class TestOpenStackRateLimitMiddlewareWithLimes(unittest.TestCase):

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
                'limes_enabled': True,
                'limes_url': 'http://localhost:5000'
            },
            memcached=fake.FakeMemcached()
        )
        self.is_setup = True