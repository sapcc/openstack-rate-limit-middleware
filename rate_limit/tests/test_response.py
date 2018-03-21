import unittest
import json

from rate_limit import response


class TestResponse(unittest.TestCase):
    def test_default_ratelimitexceededresponse(self):
        ratelimit_response = response.RateLimitExceededResponse()

        self.assertEqual(
            ratelimit_response.status_code,
            429
        )
        self.assertEqual(
            ratelimit_response.content_type,
            "application/json"
        )
        self.assertEqual(
            str(ratelimit_response.json_body),
            json.dumps({"error": {"status": "429 Too Many Requests", "message": "Too Many Requests"}})
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
