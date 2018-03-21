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

import time
import yaml

from . import errors


class Constants(object):
    """
    shared constants, primarily used to parse the configuration
    """
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

    # fetch rate limits from limes every t seconds
    limes_refresh_interval_seconds = 300


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


def is_none_or_unknown(thing):
    """
    check if a thing is None or unknown

    :param thing: the cadf action, cadf target_type_uri, ..
    :return: bool whether thing is None or unknown
    """
    return thing is None or thing == Constants.unknown


def is_unlimited(rate_limit):
    """
    check whether a rate limit is None or unlimited (indicated by '-1')

    :param rate_limit: the rate limit to check
    :return: bool
    """
    return rate_limit is None or rate_limit == -1


def is_ratelimit_by_project_id(ratelimit_by):
    """
    check whether the scope is the initiator or target project id

    :param ratelimit_by: the configurable scope by which is rate limited
    :return: bool whether the scope is initiator|target project id
    """
    return ratelimit_by == Constants.initiator_project_id or ratelimit_by == Constants.target_project_id


def find_item_by_key_in_list(item, key, list_to_search, empty_item={}):
    """
    find an item in a list by its key

    :param item: the item we're looking for
    :param key: the key by which the item can be identified
    :param list_to_search: list of items
    :param empty_item: is returned when the item could not be found
    :return:
    """
    for list_item in list_to_search:
        if list_item.get(key) == item:
            return list_item
    return empty_item


def load_config(cfg_file):
    """
    load a yaml configuration as a dictionary

    :param cfg_file: path to the yaml configuration file
    :return: the configuration as dictionary
    """
    yaml_conf = {}
    try:
        with open(cfg_file, 'r') as f:
            yaml_conf = yaml.safe_load(f)
    except IOError as e:
        raise errors.ConfigError("Failed to load configuration from file %s: %s" % (cfg_file, str(e)))
    finally:
        return yaml_conf
