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

import logging
import math
import memcache
import redis
import time

from rate_limit import common
from rate_limit import Units


logging.basicConfig(format='%(asctime)-15s %(message)s')


class Backend(object):
    """
    Backend for storing rate limits.
    """
    def __init__(self, host, port, rate_limit_response, logger, **kwargs):
        self.host = host
        self.port = port
        self.rate_limit_response = rate_limit_response
        self.logger = logger

    def rate_limit(self, scope, action, target_type_uri, max_rate_string):
        raise NotImplementedError


class RedisBackend(Backend):
    """
    Redis backend for storing rate limits.
    """
    def __init__(self, host, port, rate_limit_response, logger, **kwargs):
        super(RedisBackend, self).__init__(
            host=host,
            port=port,
            rate_limit_response=rate_limit_response,
            logger=logger,
            kwargs=kwargs
        )
        self.redis_conn_pool = redis.ConnectionPool(host=host, port=port)

    def rate_limit(self, scope, action, target_type_uri, max_rate_string):
        try:
            key = common.key_func(scope=scope, action=action, target_type_uri=target_type_uri)
            max_rate, sliding_window_seconds = Units.parse_sliding_window_rate_limit(max_rate_string)
            self.logger.debug(
                "checking rate limit for request '{0} {1}' in scope {2}".format(action, target_type_uri, scope)
            )
            return self.__rate_limit(key, sliding_window_seconds, max_rate)
        except Exception as e:
            self.logger.debug("failed to rate limit: {0}".format(str(e)))

    def __rate_limit(self, key, window_seconds, max_calls):
        now = time.time()
        lookback_seconds = now - window_seconds

        # Create a new RedisClient using the ConnectionPool.
        redis_client = redis.StrictRedis(connection_pool=self.redis_conn_pool, decode_responses=True)

        # See https://engagor.github.io/blog/2017/05/02/sliding-window-rate-limiter-redis.
        # Create a transaction block (aka pipeline) to queue multiple commands for later execution.
        pipe = redis_client.pipeline()
        # Clean out API calls that were done before the window.
        pipe.zremrangebyrank(key, 0, lookback_seconds)
        # List of API calls during sliding window.
        pipe.zrange(key, 0, -1)
        # Add current API call.
        pipe.zadd(key, now, now)
        # Reset expiry date.
        pipe.expire(key, window_seconds)
        # Execute the transaction block.
        result = pipe.execute()

        # Check whether the rate limit is exhausted.
        timestamps = result[1]
        remaining = max(0, max_calls - len(timestamps))
        if remaining > 0:
            pass
        else:
            # set RETRY-AFTER and always round up
            self.rate_limit_response.set_retry_after(math.ceil(timestamps[0] + window_seconds - now))
            return self.rate_limit_response


class MemcachedBackend(Backend):
    """
    Memcached backend for storing rate limits.
    """
    def __init__(self, host, port, rate_limit_response, logger, **kwargs):
        super(MemcachedBackend, self).__init__(
            host=host,
            port=port,
            rate_limit_response=rate_limit_response,
            logger=logger,
            kwargs=kwargs
        )
        self.memcached = memcache.Client(
            servers=[host],
            debug=1
        )

    def rate_limit(self, scope, action, target_type_uri, max_rate_string):
        try:
            max_rate, sliding_window_seconds = Units.parse_sliding_window_rate_limit(max_rate_string)
            key = common.key_func(scope, action, target_type_uri)
            self.logger.debug(
                "checking rate limit for request '{0} {1}' in scope {2}".format(action, target_type_uri, scope)
            )
            return self.__rate_limit(key, sliding_window_seconds, max_rate)
        except Exception as e:
            self.logger.error('MemcacheConnectionError: {0}'.format(e))
            return 0

    def __rate_limit(self, key, window_seconds, max_calls):
        now = time.time()

        # get list of requests that hit the api
        hit_list = self.memcached.gets(key)
        if not hit_list or not isinstance(hit_list, list):
            hit_list = []
        hit_list = self._get_hits_in_current_window(hit_list, now - window_seconds)

        rate_limit_reached = len(hit_list) + 1 > max_calls
        if rate_limit_reached:
            self.logger.debug(
                'rate limit reached key: {0}, max_rate: {1}, window_seconds: {2}'
                .format(key, max_calls, window_seconds)
            )
            # set RETRY-AFTER and always round up
            self.rate_limit_response.set_retry_after(
                math.ceil(hit_list[0] + window_seconds - now)
            )
            return self.rate_limit_response
        # update number of requests and make sure the key expires eventually to avoid polluting the memcache
        self.memcached.cas(key, hit_list + [now], time=2 * window_seconds)
        return None

    def key_with_time_window(self, scope, action, target_type_uri, time_window):
        """
        returns a key with a time window suffix, e.g. '012314af_create_servers_11-04-2018_13:00:29'

        :param scope: the scope uid of the request
        :param action: cadf action the request
        :param target_type_uri: the target type uri
        :param time_window: the sliding time window
        :return: the key with time slot prefix
        """
        return '{0}_{1}'.format(common.key_func(scope, action, target_type_uri), time_window)

    @staticmethod
    def _get_hits_in_current_window(timestamp_list, not_older_than_timestamp=time.time()):
        """
        get list of requests (actually their timestamps) that hit the api within the current sliding window.
        if any left: also expire outdated timestamps

        :param timestamp_list: list of timestamps
        :param not_older_than_timestamp: delete items older than this timestamp
        :return: the cleaned timestamp list
        """
        for ts in timestamp_list:
            if ts < not_older_than_timestamp:
                timestamp_list.remove(ts)
        return timestamp_list
