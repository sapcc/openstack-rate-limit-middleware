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


class ConfigError(Exception):
    """
    Raised when configuration could not be loaded or interpreted
    """
    pass


class MemcacheConnectionError(Exception):
    """
    Raised when connection to memcached caused an error
    """
    pass


class MaxSleepTimeHitError(Exception):
    """
    Raised when the maximal sleep time was hit for a key
    """
    pass


class UnitConversionError(Exception):
    """
    Raised when a unit is invalid and cannot be converted
    """
    pass
