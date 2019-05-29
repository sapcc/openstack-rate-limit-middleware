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
    get custom response from configuration

    :param response_config: the configuration of the response
    :return: code, headers, content_type, body, json_body
    """
    h = response_config.get("headers", {})
    headers = [(k, v) for k, v in six.iteritems(h)]
    status = response_config.get("status", None)
    body = response_config.get("body", None)
    content_type = response_config.get("content_type", None)
    json_body = response_config.get("json_body", None)
    return status, headers, content_type, body, json_body


class RateLimitExceededResponse(Response):
    """
    Defines the rate limit response and defaults, which can be overwritten via configuration.
    """
    def __init__(self, status=None, headers=None, content_type=None, body=None, json_body=None):
        """
        Creates a new RateLimitExceededResponse with either a body or json_body.

        :param status: the status code
        :param headers: list of header dictionaries
        :param body: the response body
        :param json_body: the response json body
        """
        if not status:
            status = '429 Too Many Requests'

        if body:
            super(RateLimitExceededResponse, self).__init__(
                status=status, headerlist=headers, content_type=content_type, body=body, charset="UTF-8"
            )
            return
        elif not json_body:
            content_type = "application/json"
            json_body = {"error": {"status": status, "message": "Too Many Requests"}}
        super(RateLimitExceededResponse, self).__init__(
            status=status, headerlist=headers, content_type=content_type,
            json_body=json.dumps(json_body, sort_keys=True), charset="UTF-8",
        )

    def set_headers(self, ratelimit, remaining, retry_after):
        """
        Set response headers.

        :param ratelimit: the limit for the current request in the format <n>r/<m><t>
        :param remaining: the number of remaining requests within the current window
        :param retry_after: the remaining window before the rate limit resets in seconds
        """
        if not self.headerlist:
            self.headerlist = []

        self.headerlist.append((common.Constants.header_ratelimit_retry_after, int(retry_after)))
        self.headerlist.append((common.Constants.header_ratelimit_reset, int(retry_after)))
        self.headerlist.append((common.Constants.header_ratelimit_limit, str(ratelimit)))
        self.headerlist.append((common.Constants.header_ratelimit_remaining, int(remaining)))


class BlacklistResponse(Response):
    """
    defines the blacklist response and defaults, which can be overwritten via configuration.
    """
    def __init__(self, status=None, headers=None, content_type=None, body=None, json_body=None):
        """
        creates a new BlacklistResponse with either a body or json_body

        :param status: the status code
        :param headers: list of header dictionaries
        :param body: the response body
        :param json_body: the response json body
        """
        if not status:
            status = '497 Blacklisted'

        if body:
            super(BlacklistResponse, self).__init__(
                status=status, headerlist=headers, content_type=content_type, body=body, charset="UTF-8"
            )
            return
        elif not json_body:
            content_type = "application/json"
            json_body = {"error": {"status": status, "message": "You have been blacklisted"}}
        super(BlacklistResponse, self).__init__(
            status=status, headerlist=headers, content_type=content_type,
            json_body=json.dumps(json_body, sort_keys=True), charset="UTF-8"
        )
