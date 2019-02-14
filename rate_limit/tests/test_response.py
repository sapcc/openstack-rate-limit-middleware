import os
import unittest
import json

from rate_limit import common
from rate_limit import response


WORKDIR = os.path.dirname(os.path.realpath(__file__))
SWIFTCONFIGPATH = WORKDIR + '/fixtures/swift.yaml'


class TestResponse(unittest.TestCase):
    def test_default_ratelimitexceededresponse_json(self):
        ratelimit_response = response.RateLimitExceededResponse()

        self.assertEqual(
            ratelimit_response.status_code,
            429
        )
        self.assertEqual(
            ratelimit_response.content_type,
            "application/json"
        )

        actual_body = sorted(json.loads(ratelimit_response.json_body))
        expected_body = sorted(json.loads('{"error": {"status": "429 Too Many Requests", "message": "Too Many Requests"}}'))

        self.assertEqual(
            actual_body,
            expected_body
        )

    def test_custom_ratelimitexceededresponse_html(self):
        conf = common.load_config(SWIFTCONFIGPATH)
        status, headers, content_type, body, json_body = response.response_parameters_from_config(conf.get('ratelimit_response'))

        ratelimit_response = response.RateLimitExceededResponse(
            status=status,
            headers=headers,
            content_type=content_type,
            body=body,
            json_body=json_body
        )

        self.assertEqual(
            ratelimit_response.status,
            '498 Rate Limited',
            "expected ratelimit response status '498 Rate Limited' but got '{0}'"
            .format(ratelimit_response.status)
        )
        self.assertEqual(
            ratelimit_response.body,
            'Rate Limit Exceeded',
            "expected ratelimit response body 'Rate Limit Exceeded' but got '{0}'"
            .format(ratelimit_response.status)
        )

        h = ratelimit_response.headers.get('X-FOO', None)

        print "-------------------------------------------------------"
        print h
        self.assertEqual(
            str(h),
            'RateLimitFoo',
            "expected ratelimit response headers '{'X-FOO': 'RateLimitFoo'}'"
        )

    def test_default_blacklistexceededresponse(self):
        blacklist_response = response.BlacklistResponse()

        self.assertEqual(
            blacklist_response.status_code,
            497
        )
        self.assertEqual(
            blacklist_response.content_type,
            "application/json"
        )
        self.assertEqual(
            str(blacklist_response.json_body),
            json.dumps({"error": {"status": "497 Blacklisted", "message": "You have been blacklisted"}})
        )


if __name__ == '__main__':
    unittest.main()
