# Copyright 2019 SAP SE
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

import json
import six
from webob import Response

from . import common


def response_parameters_from_config(response_config):
    """
    Get custom response from configuration.

    :param response_config: the configuration of the response
    :return: code, headers, content_type, body, json_body
    """
    h = response_config.get("headers", {})
    headers = [(k, v) for k, v in six.iteritems(h)]
    status = response_config.get("status", None)
    status_code = response_config.get("status_code", None)
    body = response_config.get("body", None)
    json_body = response_config.get("json_body", None)
    return status, status_code, headers, body, json_body


class RateLimitExceededResponse(Response):
    """The rate limit response and defaults, which can be overwritten via configuration."""

    def __init__(self, status='429 Too Many Requests', status_code=429, headerlist=None,
                 body=None, json_body=None, environ=None):
        """
        Create a new RateLimitExceededResponse with either a body or json_body.

        :param status: the status code
        :param headerlist: list of header tuples
        :param body: the response body
        :param json_body: the response json body
        :param environ: the environ of the request triggering this response
        """
        super(RateLimitExceededResponse, self).__init__(headerlist=headerlist, charset="UTF-8")

        self.status_code = status_code
        self.status = status
        self.environ = environ

        if body:
            self.content_type = common.Constants.content_type_html
            if isinstance(body, six.text_type):
                body = body.encode('utf8')
            self.body = body
            return

        # Set a default json body.
        if not json_body:
            json_body = {"error": {"status": status, "message": "Too Many Requests"}}

        self.content_type = common.Constants.content_type_json
        self.json_body = json.dumps(json_body, sort_keys=True)

    def set_headers(self, ratelimit, remaining, retry_after):
        """
        Set response headers.

        :param ratelimit: the limit for the current request in the format <n>r/<m><t>
        :param remaining: the number of remaining requests within the current window
        :param retry_after: the remaining window before the rate limit resets in seconds
        """
        self.headers[common.Constants.header_ratelimit_retry_after] = int(retry_after)
        self.headers[common.Constants.header_ratelimit_reset] = int(retry_after)
        self.headers[common.Constants.header_ratelimit_limit] = str(ratelimit)
        self.headers[common.Constants.header_ratelimit_remaining] = int(remaining)

    def set_environ(self, environ):
        """Set the environ of the request triggering this response."""
        self.environ = environ


class BlacklistResponse(Response):
    """The blacklist response and defaults, which can be overwritten via configuration."""

    def __init__(self, status='497 Blacklisted', status_code=497, headerlist=None,
                 body=None, json_body=None, environ=None):
        """
        Create a new BlacklistResponse with either a body or json_body.

        :param status: the status code
        :param headerlist: list of header dictionaries
        :param body: the response body
        :param json_body: the response json body
        :param request: the request triggering this response
        """
        super(BlacklistResponse, self).__init__(headerlist=headerlist, charset="UTF-8")

        self.status_code = status_code
        self.status = status
        self.environ = environ

        if body:
            self.content_type = common.Constants.content_type_html
            if isinstance(body, six.text_type):
                body = body.encode('utf8')
            self.body = body
            return

        # Set a default json body.
        if not json_body:
            json_body = {"error": {"status": status, "message": "You have been blacklisted"}}

        self.content_type = common.Constants.content_type_json
        self.json_body = json.dumps(json_body, sort_keys=True)

    def set_environ(self, environ):
        """Set the environ of the request triggering this response."""
        self.environ = environ
