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

from enum import Enum


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
        try:
            value, unit = str(value_string).split('r/')
            if not value or not unit:
                return -1.0

            value = float(value)
            if 0 < value < 1:
                value = 1.0
            elif value < 0:
                value = -1.0
            return round(value / Units.get_conversion_factor(unit), decimal_places)
        except ValueError:
            return -1.0

    @staticmethod
    def parse_sliding_window_rate_limit(value_string):
        """
        parses sliding window rate limit definition like '2r/m' or '2r/15m'

        :param value_string: rate limit as string, e.g. '2r/m'
        :return: the value and unit
        """
        try:
            value, unit_string = value_string.split('r/')
            unit_seconds = Units.parse(unit_string)
            return float(value), float(unit_seconds)
        except ValueError:
            return -1.0, 1.0

    @staticmethod
    def parse(value_string):
        """
        parses value_string like '1m' and returns value in seconds

        :param value_string: the value string to parse
        :return: the value in seconds
        """
        try:
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
        except ValueError:
            return -1.0
