import json
import os
import six
import unittest


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
            common.Constants.content_type_json,
            "expected response content type to be equal. want '{0}' but got '{1}'".format(common.Constants.content_type_json, ratelimit_response.content_type)
        )

        actual_body = sorted(json.loads(ratelimit_response.json_body))
        expected_body = sorted(json.loads(
            '{"error": {"status": "429 Too Many Requests", "message": "Too Many Requests"}}'
        ))

        self.assertEqual(
            expected_body,
            actual_body,
            "expected response bodies to be equal. want '{0}' but got '{1}'".format(expected_body, actual_body)
        )

    def test_custom_ratelimitexceededresponse_html(self):
        conf = common.load_config(SWIFTCONFIGPATH)
        status, status_code, headers, body, json_body = response.response_parameters_from_config(conf.get(common.Constants.ratelimit_response))

        ratelimit_response = response.RateLimitExceededResponse(
            status=status,
            status_code=status_code,
            headerlist=headers,
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
            ratelimit_response.status_code,
            498,
            "expected ratelimit response status code '498' but got '{0}'".format(ratelimit_response.status_code)
        )

        self.assertEqual(
            ratelimit_response.content_type,
            common.Constants.content_type_html,
            "expected ratelimit response content type '{0}' but got '{1}'"
            .format(common.Constants.content_type_html, ratelimit_response.content_type)
        )

        self.assertEqual(
            ratelimit_response.body.decode('utf-8'),
            'Rate Limit Exceeded',
            "expected ratelimit response body 'Rate Limit Exceeded' but got '{0}'"
            .format(ratelimit_response.body)
        )

        h = ratelimit_response.headers.get('X-Foo', None)
        self.assertEqual(
            str(h),
            'RateLimitFoo',
            "expected ratelimit response headers '{'X-FOO': 'RateLimitFoo'}'"
        )

    def test_default_blacklistresponse(self):
        blacklist_response = response.BlacklistResponse()

        self.assertEqual(
            blacklist_response.status,
            '497 Blacklisted',
            "expected blacklist response status '497 Blacklisted' but got '{0}'".format(blacklist_response.status)
        )

        self.assertEqual(
            blacklist_response.status_code,
            497,
            "expected blacklist response status code to be '497' but got '{0}'".format(blacklist_response.status_code)
        )

        self.assertEqual(
            blacklist_response.content_type,
            common.Constants.content_type_json,
            "expected blacklist response content type to be '{0}' but got '{1}'"
            .format(common.Constants.content_type_json, blacklist_response.content_type)
        )

        expected_json_body = json.dumps({"error": {"status": "497 Blacklisted", "message": "You have been blacklisted"}}, sort_keys=True)
        self.assertEqual(
            blacklist_response.json_body,
            expected_json_body,
            "expected blacklist response body to be '{0}' but got '{1}'".format(expected_json_body, blacklist_response.json_body)
        )

    def test_custom_blacklistresponse_json(self):
        conf = common.load_config(SWIFTCONFIGPATH)
        status, status_code, headers, body, json_body = response.response_parameters_from_config(conf.get(common.Constants.blacklist_response))

        blacklist_response = response.BlacklistResponse(
            status=status,
            status_code=status_code,
            headerlist=headers,
            body=body,
            json_body=json_body
        )

        self.assertEqual(
            blacklist_response.status,
            '497 Blacklisted',
            "expected blacklist response status '497 Blacklisted' but got '{0}'"
            .format(blacklist_response.status)
        )

        self.assertEqual(
            blacklist_response.status_code,
            497,
            "expected blacklist response status code '497' but got '{0}'".format(blacklist_response.status_code)
        )

        self.assertEqual(
            blacklist_response.content_type,
            common.Constants.content_type_json,
            "expected blacklist response content type '{0}' but got '{1}'"
            .format(common.Constants.content_type_json, blacklist_response.content_type)
        )

        expected_json_body = json.dumps({"error": {"status": "497 Blacklisted", "message": "You have been blacklisted. Please contact and administrator."}}, sort_keys=True)
        self.assertEqual(
            blacklist_response.json_body,
            expected_json_body,
            "expected blacklist response json_body '{0}' but got '{1}'"
            .format(expected_json_body, blacklist_response.body)
        )

        h = blacklist_response.headers.get('X-Foo', None)
        self.assertEqual(
            str(h),
            'Bar',
        )


if __name__ == '__main__':
    unittest.main()
