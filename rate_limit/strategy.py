# Copyright 2018 SAP SE
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
import math
import time

from .common import Units, key_func
from .errors import MaxSleepTimeHitError, MemcacheConnectionError
from .response import RateLimitExceededResponse


class RateLimitStrategy(object):
    """
    Base class for rate limit strategies using memcached.
    Assumption: Whether rate limit is applied or not is checked beforehand.
    """
    def __init__(self, logger, memcached, key_function, rate_limit_response, clock_accuracy, strategy_name):
        self.logger = logger
        self.memcached = memcached
        self.key_func = key_function
        self.rate_limit_response = rate_limit_response
        self.clock_accuracy = clock_accuracy
        self.strategy_name = strategy_name

    def rate_limit(self, scope, action, target_type_uri, max_rate_limit):
        """
        Contains the rate limit logic
        """
        pass

    def key_func(self, scope, action, target_type_uri):
        """
        Defines how a key is created
        """
        pass


class FixedWindowStrategy(RateLimitStrategy):
    """
    The FixedWindowStrategy enables simple scenarios to provide a basic protection for backends against a high number of
    requests. For example: 1 request per second, 10 requests per minute.

    Limitations: This strategy makes most sense when the base unit is seconds or when the requests-per-time-ratio is
    high. Refer to the documentation for more details.
    """

    def __init__(self, logger, memcached, max_sleep_time_seconds=20, rate_buffer_seconds=20, clock_accuracy=1000,
                 rate_limit_response=RateLimitExceededResponse):

        super(FixedWindowStrategy, self).__init__(
            logger=logger, memcached=memcached, key_function=key_func,
            rate_limit_response=rate_limit_response,
            clock_accuracy=clock_accuracy, strategy_name='Default'
        )
        self.max_sleep_time_seconds = max_sleep_time_seconds
        self.rate_buffer_seconds = rate_buffer_seconds

    def rate_limit(self, scope, action, target_type_uri, max_rate_string):
        key = key_func(scope, action, target_type_uri)
        try:
            sleep_time = self._get_sleep_time(key, max_rate_string)
        except MaxSleepTimeHitError as e:
            self.logger.info(
                "rate limit reached for request: {0} {1} in scope {2}: {3}"
                .format(action, target_type_uri, scope, e)
            )
            return self.rate_limit_response

        if sleep_time > 0:
            self.logger.info(
                'queueing request: {0} {1}, scope: {2} waiting {3}s'.format(action, target_type_uri, scope, sleep_time)
            )
            # queue request
            eventlet.sleep(sleep_time)
        return None

    def _get_sleep_time(self, key, max_rate_string):
        """
        Determines if the request has to sleep.

        :param key: the key identifying the request
        :param max_rate_string: the maximal number of requests per interval
        :return: the sleep time
        """
        self.logger.info('checking sleep time for {0} with max_rate: {1}'.format(key, max_rate_string))
        max_rate = Units.parse_and_convert_to_per_seconds(max_rate_string)
        if max_rate == 0:
            return 0
        now = int(round(time.time() * self.clock_accuracy))
        time_per_request = int(round(self.clock_accuracy / max_rate))

        try:
            running_time = self.memcached.incr(key, delta=time_per_request) or 0
            need_to_sleep = 0
            if (now - running_time) > (self.rate_buffer_seconds * self.clock_accuracy):
                next_avail_time = int(now + time_per_request)
                self.memcached.set(key, str(next_avail_time))
            else:
                need_to_sleep = max(running_time - now - time_per_request, 0)

            max_sleep = self.max_sleep_time_seconds * self.clock_accuracy
            if max_sleep - need_to_sleep <= self.clock_accuracy * 0.01:
                # treat as no-op decrement time
                self.memcached.decr(key, delta=time_per_request)
                raise MaxSleepTimeHitError(
                    'max sleep time exceeded: %.2f' %
                    (float(need_to_sleep) / self.clock_accuracy))

            return float(need_to_sleep) / self.clock_accuracy

        except MemcacheConnectionError as e:
            self.logger.error('MemcacheConnectionError: %s' % str(e))
            return 0


class SlidingWindowStrategy(RateLimitStrategy):
    """
    The SlidingWindowStrategy enables more complex rate limiting scenarios and allows the configuration of a time window,
    in which rate limits are applied. For example: 5 requests per 15 minutes, 100 requests per 1 hour, etc.

    Limitations: The SlidingWindowStrategy can only be used when the base unit is minutes or more (requests per minute,
    requests per hour, requests per day, etc.)
    The time window is stored and loaded as part of the key -which takes time- and thus this strategy cannot be used to
    reflect requests per second rate limit scenarios.

    Summary of the SlidingWindowStrategy algorithm:
    (1) Define a sliding window. For example a window of 1 minute: '11-04-2018_13:00'
    (2) Increase
    """
    def __init__(self, logger, memcached, clock_accuracy, rate_limit_response=RateLimitExceededResponse):
        super(SlidingWindowStrategy, self).__init__(
            logger=logger, memcached=memcached,
            key_function=SlidingWindowStrategy.key_with_time_window,
            clock_accuracy=clock_accuracy,
            rate_limit_response=rate_limit_response,
            strategy_name='SlidingWindow'
        )

    def rate_limit(self, scope, action, target_type_uri, max_rate_string):
        self.logger.info(
            "checking rate limit for request '{0} {1}' in scope {2}".format(action, target_type_uri, scope)
        )

        try:
            max_rate, sliding_window_seconds = Units.parse_sliding_window_rate_limit(max_rate_string)
            key = key_func(scope, action, target_type_uri)
            now = time.time()

            # get list of requests that hit the api
            hit_list = self.memcached.gets(key)
            if not hit_list or not isinstance(hit_list, list):
                hit_list = []
            hit_list = self._get_hits_in_current_window(hit_list, now - sliding_window_seconds)

            rate_limit_reached = len(hit_list) + 1 > max_rate
            if rate_limit_reached:
                self.logger.info(
                    'rate limit of {0} reached for request: {1} {2} in scope {3}'
                    .format(max_rate_string, action, target_type_uri, scope)
                )
                # set RETRY-AFTER and always round up
                self.rate_limit_response.set_retry_after(
                    math.ceil(hit_list[0] + sliding_window_seconds - now)
                )
                return self.rate_limit_response
            self.memcached.cas(key, hit_list + [now])

            return None

        except Exception as e:
            self.logger.error('MemcacheConnectionError: {0}'.format(e))
            return 0

    @staticmethod
    def key_with_time_window(scope, action, target_type_uri, time_window):
        """
        returns a key with a time window suffix, e.g. '012314af_create_servers_11-04-2018_13:00:29'

        :param scope: the scope uid of the request
        :param action: cadf action the request
        :param target_type_uri: the target type uri
        :param time_window: the sliding time window
        :return: the key with time slot prefix
        """
        return '{0}_{1}'.format(key_func(scope, action, target_type_uri), time_window)

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
