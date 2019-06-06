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

import time
import yaml

from . import errors


CADF_SERVICE_TYPE_PREFIX_MAP = {
    'key-manager': 'service/security/keymanager',
    'volume': 'service/storage/block',
    'baremetal': 'service/compute/baremetal',
    'share': 'service/storage/share',
    'identity': 'data/security',
    'dns': 'service/dns',
    'network': 'service/network',
    'compute': 'service/compute',
    'image': 'service/storage/image'
}


class Constants(object):
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

    backend_redis = 'redis'
    backend_memcache = 'memcache'

    # The limit for the current request in the format <n>r/<m><t>.
    # Read: Limit to n requests per m <unit>. Valid interval units are `s, m, h, d`.
    header_ratelimit_limit = 'X-RateLimit-Limit'

    # The number of remaining requests within the current window.
    header_ratelimit_remaining = 'X-RateLimit-Remaining'

    # The remaining window before the rate limit resets in seconds.
    header_ratelimit_reset = 'X-RateLimit-Retry-After'

    # For compatibility with OpenStack Swift. Same as 'header_ratelimit_reset'.
    header_ratelimit_retry_after = 'X-Retry-After'

    # Response content type.
    content_type_json = "application/json"


def key_func(scope, action, target_type_uri):
    """
    Create the key based on scope, action, target_type_uri: '<scope>_<action>_<target_type_uri>'.
    If no scope is given (scope=None), the scope is global (global, non-project specific rate limits).

    :param scope: the identifier of the scope (project uid, user uid, ip addr, ..) or 'global'
    :param action: the cadf action
    :param target_type_uri: the target type uri of the request
    :return: the key '<scope>_<action>_<target_type_uri>'
    """
    return 'ratelimit_{0}_{1}_{2}'.format('global' if scope is None else scope, action, target_type_uri)


def printable_timestamp(timestamp):
    gmtime = time.gmtime(timestamp)
    return str(gmtime.tm_hour) + ':' + str(gmtime.tm_min) + ':' + str(gmtime.tm_sec)


def is_none_or_unknown(thing):
    """
    Check if a thing is None or unknown.

    :param thing: the cadf action, cadf target_type_uri, ..
    :return: bool whether thing is None or unknown
    """
    return thing is None or thing == Constants.unknown


def is_unlimited(rate_limit):
    """
    Check whether a rate limit is None or unlimited (indicated by '-1').

    :param rate_limit: the rate limit to check
    :return: bool
    """
    return rate_limit is None or rate_limit == -1


def is_ratelimit_by_project_id(ratelimit_by):
    """
    Check whether the scope is the initiator or target project id.

    :param ratelimit_by: the configurable scope by which is rate limited
    :return: bool whether the scope is initiator|target project id
    """
    return ratelimit_by == Constants.initiator_project_id or ratelimit_by == Constants.target_project_id


def find_item_by_key_in_list(item, key, list_to_search, empty_item={}):
    """
    Find an item in a list by its key.

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
    Load a yaml configuration as a dictionary.

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
