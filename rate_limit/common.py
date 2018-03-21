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

import re
import time

from enum import Enum


# shared constants
class Constants(object):
    """
    shared constants, primarily used to parse the configuration
    """
    rate_limits = 'rates'
    ratelimit_response = 'ratelimit_response'
    blacklist_response = 'blacklist_response'
    max_sleep_time_seconds = 'max_sleep_time_seconds'
    rate_buffer_seconds = 'rate_buffer_seconds'
    clock_accuracy = 'clock_accuracy'
    unknown = 'unknown'

    # rate limit by ..
    initiator_project_id = 'initiator_project_id'
    initiator_host_address = 'initiator_host_address'
    target_project_id = 'target_project_id'


class Units(Enum):
    """
    defines the units that can be used to rate limit requests
    """
    MILLISECOND = 'ms'
    SECOND = 's'
    MINUTE = 'm'
    HOUR = 'h'
    DAY = 'd'

    @staticmethod
    def get_conversion_factor(unit):
        f = -1
        if unit == Units.MILLISECOND.value:
            f = 0.001
        elif unit == Units.SECOND.value:
            f = 1
        elif unit == Units.MINUTE.value:
            f = 60.0
        elif unit == Units.HOUR.value:
            f = 60 * 60.0
        elif unit == Units.DAY.value:
            f = 24 * 60 * 60.0
        return f

    @staticmethod
    def parse_and_convert_to_per_seconds(value_string, decimal_places=4):
        """
        parses value_string like '1r/s' and returns 1

        :param value_string: rate limit as string
        :param decimal_places: precision of the result
        :return: the rate limit per second
        """
        value, unit = str(value_string).split('r/')
        if not value or not unit:
            return -1.0

        value = float(value)
        if 0 < value < 1:
            value = 1.0
        elif value < 0:
            value = -1.0
        return round(value / Units.get_conversion_factor(unit), decimal_places)

    @staticmethod
    def parse_sliding_window_rate_limit(value_string):
        """
        parses sliding window rate limit definition like '2r/m' or '2r/15m'

        :param value_string: rate limit as string, e.g. '2r/m'
        :return: the value and unit
        """
        value, unit_string = value_string.split('r/')
        unit_seconds = Units.parse(unit_string)
        return float(value), float(unit_seconds)

    @staticmethod
    def parse(value_string):
        """
        parses value_string like '1m' and returns value in seconds

        :param value_string:
        :return:
        """
        regex = re.compile('(?P<value>\d*)(?P<unit>\w+)')
        result = regex.match(value_string)
        if not result:
            return -1
        value = result.group('value') or 1
        unit = result.group('unit')
        f = Units.get_conversion_factor(unit)
        if f == -1:
            return f
        return float(value) * f


def key_func(scope, action, target_type_uri):
    """
    creates the key based on scope, action, target_type_uri: '<scope>_<action>_<target_type_uri>'

    :param scope: the identifier of the scope (project uid, user uid, ip addr, ..)
    :param action: the cadf action
    :param target_type_uri: the target type uri of the request
    :return: the key '<scope>_<action>_<target_type_uri>'
    """
    return 'ratelimit_{0}_{1}_{2}'.format(scope, action, target_type_uri)


def printable_timestamp(timestamp):
    gmtime = time.gmtime(timestamp)
    return str(gmtime.tm_hour) + ':' + str(gmtime.tm_min) + ':' + str(gmtime.tm_sec)
