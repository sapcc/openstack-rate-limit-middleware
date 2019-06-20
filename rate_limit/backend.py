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

import eventlet
import hashlib
import logging
import redis
import time

from distutils.version import StrictVersion

from . import common
from .units import Units

logging.basicConfig(format='%(asctime)-15s %(message)s')


class Backend(object):
    """Backend for storing rate limits."""

    def __init__(self, host, port, rate_limit_response, logger, **kwargs):
        self.__host = host
        self.__port = port
        self.__rate_limit_response = rate_limit_response
        self.logger = logger

    def rate_limit(self, scope, action, target_type_uri, max_rate_string):
        """
        Handle the rate limit for the given scope, action, target_type_uri and max_rate_string.
        If scope is not given (scope=None) the global (non-project specific) rate limit is checked.

        :param scope: the scope (project uuid, host ip, etc., ..) or None for global rate limits
        :param action: the CADF action
        :param target_type_uri: the CADF target type URI
        :param max_rate_string: the max. rate limit per sliding window
        :return: the configured RateLimitResponse or None
        """
        return None

    def is_available(self):
        """
        Check whether the backend is available and the version supported.

        :return: bool whether it's available, string describing the error (if any)
        """
        return True, ""


class RedisBackend(Backend):
    """Stable Redis backend for storing rate limits."""

    def __init__(self, host, port, rate_limit_response, max_sleep_time_seconds, log_sleep_time_seconds, logger, **kwargs):
        super(RedisBackend, self).__init__(
            host=host,
            port=port,
            rate_limit_response=rate_limit_response,
            max_sleep_time_seconds=max_sleep_time_seconds,
            log_sleep_time_seconds=log_sleep_time_seconds,
            logger=logger,
            kwargs=kwargs
        )
        self.__host = host
        self.__port = port
        self.__max_sleep_time_seconds = max_sleep_time_seconds
        self.__log_sleep_time_seconds = log_sleep_time_seconds
        self.__rate_limit_response = rate_limit_response
        self.__timeout = kwargs.get('timeout_seconds', 20)
        self.__max_connections = kwargs.get('max_connections', 100)
        # Default to nanosecond accuracy.
        self.__clock_accuracy = int(kwargs.get('clock_accuracy', 1e6))

        # Use a thread-safe blocking connection pool.
        conn_pool = redis.BlockingConnectionPool(
            host=host, port=port, max_connections=self.__max_connections, timeout=self.__timeout,
        )
        self.__redis = redis.StrictRedis(
            connection_pool=conn_pool, decode_responses=True,
            socket_timeout=self.__timeout, socket_connect_timeout=self.__timeout,
        )

        script_name = "redis_sliding_window.lua"
        script = common.load_lua_script(script_name)
        if not script:
            self.logger.error(
                "error loading rate limit script: '{0}'".format(script_name)
            )
            return
        self.__rate_limit_script = script
        self.__rate_limit_script_sha = hashlib.sha1(script.encode('utf-8')).hexdigest()

    def is_available(self):
        """Check whether the redis is available and supported."""
        if not self.__is_redis_available():
            return False, "rate limit failed. redis not available. host='{0}', port='{1}'".format(self.__host, str(self.__port))
        if not self.__is_redis_version_supported():
            return False, "redis version not supported. need at least redis 3.0.0"
        return True, ""

    def __is_redis_available(self):
        """
        Test whether redis backend is available.

        :return: bool
        """
        try:
            # Invoke get to test redis connection.
            # Will return None or one of the following exceptions.
            self.__redis.get("")
        except (redis.exceptions.ConnectionError, redis.exceptions.BusyLoadingError):
            return False
        return True

    def __is_redis_version_supported(self):
        """
        Check whether the redis version is supported by this middleware.
        We require at least redis version 5.0.0 .

        :return: bool
        """
        version = self.__redis.info().get('redis_version', None)
        if not version:
            return False
        return bool(StrictVersion(version) >= StrictVersion('5.0.0'))

    def rate_limit(self, scope, action, target_type_uri, max_rate_string):
        """
        Handle the rate limit for the given scope, action, target_type_uri and max_rate_string.
        If scope is not given (scope=None) the global (non-project specific) rate limit is checked.

        :param scope: the scope (project uuid, host ip, etc., ..) or None for global rate limits
        :param action: the CADF action
        :param target_type_uri: the CADF target type URI
        :param max_rate_string: the max. rate limit per sliding window
        :return: the configured RateLimitResponse or None
        """
        try:
            key = common.key_func(scope=scope, action=action, target_type_uri=target_type_uri)
            max_rate, sliding_window_seconds = Units.parse_sliding_window_rate_limit(max_rate_string)
            self.logger.debug(
                "checking rate limit for request '{0} {1}' in scope {2}".format(action, target_type_uri, scope)
            )
            return self.__rate_limit(key, sliding_window_seconds, max_rate, max_rate_string)
        except Exception as e:
            self.logger.debug("failed to rate limit: {0}".format(str(e)))

    def __rate_limit(self, key, window_seconds, max_calls, max_rate_string):
        # Timestamp with given accuracy as integer.
        now_int = int(time.time() * self.__clock_accuracy)
        # Sliding window in seconds with given accuracy.
        window_seconds_int = int(window_seconds * self.__clock_accuracy)
        # Max. lookback as timestamp.
        lookback_time_max = int(now_int - window_seconds_int)
        # Make sure it's an int.
        max_calls_int = int(max_calls)

        # Use the SHA1 digest of the LUA script and use redis internal caching instead of sending it every time.
        try:
            result = self.__redis.evalsha(
                self.__rate_limit_script_sha, 7,
                key, lookback_time_max, now_int, max_calls_int, window_seconds_int, self.__max_sleep_time_seconds,
                self.__clock_accuracy,
            )
        # If the script is not (yet) present submit to redis and evaluate it.
        except redis.exceptions.NoScriptError:
            result = self.__redis.eval(
                self.__rate_limit_script, 7,
                key, lookback_time_max, now_int, max_calls_int, window_seconds_int, self.__max_sleep_time_seconds,
                self.__clock_accuracy
            )

        # Parse result list safely.
        remaining = common.listitem_to_int(result, idx=0)
        retry_after_seconds = common.listitem_to_int(result, idx=1)

        # Return here if we still have remaining requests.
        if remaining > 0:
            return None

        # Suspend the current request if its it has to wait no longer than max_sleep_time_seconds.
        elif retry_after_seconds <= self.__max_sleep_time_seconds:
            # Log the current request if it has to be suspended for at least log_sleep_time_seconds.
            if retry_after_seconds >= self.__log_sleep_time_seconds:
                self.logger.info(
                    "suspending request '{0}' for '{1}' seconds to fit rate limit '{2}'"
                    .format(key, retry_after_seconds, max_rate_string)
                )
            eventlet.sleep(retry_after_seconds)
            return None

        # If rate limit exceeded and the request cannot be suspended return the rate limit response.
        # Set headers for rate limit response.
        self.__rate_limit_response.set_headers(
            ratelimit=max_rate_string,
            remaining=remaining,
            retry_after=retry_after_seconds
        )
        return self.__rate_limit_response
