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

from rate_limit.utils import monkeypatch_crc_ccitt
monkeypatch_crc_ccitt()

import keystoneclient.v3 as keystonev3
import re
import pyredis
import requests

from keystoneauth1.identity import v3
from keystoneauth1 import session

from . import common
from . import log

from rate_limit.units import Units
NOT_DEFINED_LIMIT = -1


class BaseRateLimit:
    def __init__(self, action, scope, target_type_uri, limit):
        self.limit = limit
        self.action = action
        self.scope = scope
        self.target_type_uri = target_type_uri

    def get_time_window_key(self):
        return 'ratelimit_{0}_{1}_{2}'.format('global' if self.scope is None else self.scope, self.action, self.target_type_uri)

    def parse_sliding_window_rate_limit(self):
        """
        Parse sliding window rate limit definition.

        Example:
        (a) 2r/m  => 2, 60
        (b) 2r/5m => 2, 300

        :return: the max number of requests and sliding window in seconds
        """
        try:
            value, unit_string = self.limit.split('r/')
            unit_seconds = Units.parse(unit_string)
            return float(value), float(unit_seconds)
        except ValueError:
            return -1.0, 1.0

    def __eq__(self, other):
        """Compare two rate limits."""
        return self.limit == other

    def __str__(self):
        """
        Return the string representation of the rate limit.
        E.g. 2r/m'
        """
        return self.limit


class URIRateLimit(BaseRateLimit):
    def __init__(self, limit, target_type_uri, scope, action):
        super().__init__(action, scope, target_type_uri, limit)


class BucketRateLimit(BaseRateLimit):
    def __init__(self, action, scope, target_type_uri, limit, bucket_name):
        super().__init__(action, scope, target_type_uri, limit)
        self.bucket_name = bucket_name

    def get_time_window_key(self):
        return 'ratelimit_{0}_{1}_{2}'.format('global' if self.scope is None else self.scope, self.action,
                                              self.bucket_name)

    def __str__(self):
        """Return the string representation of the rate limit including the bucketname."""
        return f"{self.bucket_name}: {self.limit}"


class RateLimitProvider(object):
    """Interface to obtain rate limits from different sources."""

    def __init__(self, service_type, logger=log.Logger(__name__), **kwargs):
        self.service_type = service_type
        self.logger = logger
        # Global rate limits counted across all scopes.
        self.global_ratelimits = {}
        # Local rate limits counted per scope.
        self.local_ratelimits = {}
        self.buckets_ratelimits = {}

    def get_global_rate_limits(self, action, target_type_uri, **kwargs):
        """
        Get the global rate limit per action and target type URI.
        Returns -1 if unlimited.

        :param action: the CADF action for the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters
        :return: the global rate limit or -1 if not set
        """
        return NOT_DEFINED_LIMIT

    def get_local_rate_limits(self, scope, action, target_type_uri, **kwargs):
        """
        Get the local (project/domain/ip, ..) rate limit per scope, action, target type URI.

        :param scope: the UUID of the project, domain or the IP
        :param action: the CADF action of the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters
        :return: the local rate limit or -1 if not set
        """
        return NOT_DEFINED_LIMIT


class ConfigurationRateLimitProvider(RateLimitProvider):
    """The provider to obtain rate limits from a configuration file."""

    def __init__(self, service_type, logger=log.Logger(__name__), **kwargs):
        super(ConfigurationRateLimitProvider, self).__init__(
            service_type=service_type, logger=logger, kwargs=kwargs
        )

    def extract_action_based_limit(self, action, target_type_uri, scope, ttu_ratelimits):
        for rl in ttu_ratelimits:
            if action == rl.get('action'):
                ratelimit = rl.get('limit', None)
                if ratelimit:
                    return URIRateLimit(ratelimit, target_type_uri, scope, action)

                # grouping multiple rate limits in a bucket
                bucket_name = rl.get('bucket')
                if bucket_name:
                    ratelimit = self.buckets_ratelimits.get(bucket_name, {}).get("limit", NOT_DEFINED_LIMIT)
                    return BucketRateLimit(action, scope, target_type_uri, ratelimit, bucket_name)
        return URIRateLimit(NOT_DEFINED_LIMIT, target_type_uri, scope, action)

    def get_global_rate_limits(self, action, target_type_uri, **kwargs):
        """
        Get the global rate limit per action and target type URI.
        Returns -1 if unlimited.

        :param action: the CADF action for the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters
        :return: the global rate limit or -1 (unlimited) if not set
        """
        ttu_ratelimits = self.global_ratelimits.get(target_type_uri, [])
        self.logger.debug(f"Found global rate-limits {ttu_ratelimits} for "
                          f"action={action}, target_type_uri={target_type_uri}")
        if not ttu_ratelimits:
            ttu_ratelimits = self._get_wildcard_ratelimits(
                self.global_ratelimits,
                target_type_uri,
            )
        return self.extract_action_based_limit(action, target_type_uri, None, ttu_ratelimits)

    def get_local_rate_limits(self, scope, action, target_type_uri, **kwargs):
        """
        Get the local (project/domain/ip, ..) rate limit per scope, action, target type URI.

        :param scope: the UUID of the project, domain or the IP
        :param action: the CADF action of the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters
        :return: the local rate limit or -1 if not set
        """
        ttu_ratelimits = self.local_ratelimits.get(target_type_uri, [])
        self.logger.debug(f"Found local rate-limits {ttu_ratelimits} for scope={scope}, "
                          f"action={action}, target_type_uri={target_type_uri}")
        if not ttu_ratelimits:
            ttu_ratelimits = self._get_wildcard_ratelimits(
                self.local_ratelimits,
                target_type_uri,
            )
        return self.extract_action_based_limit(action, target_type_uri, scope, ttu_ratelimits)

    def _get_wildcard_ratelimits(self, ratelimits, target_type_uri):
        """Get the target type URI rate limits from wildcard pattern.

        :param target_type_uri: the target type URI of the request
        :return: target type uri ratelimits if exists
        """
        ttu_ratelimits = []
        pattern_list = [
            lr_key for lr_key in ratelimits
            if lr_key.endswith('*')
        ]
        if pattern_list:
            matched, ttu_key = self._match(target_type_uri, pattern_list)
            if matched:
                ttu_ratelimits = ratelimits[ttu_key]
        return ttu_ratelimits

    def _match(self, uri, pattern_list):
        """
        Check if a URI matches to one of the patterns.

        :param uri: URI to check if it matches to one of the patterns
        :param pattern_list : patterns to match against the URI
        :return: True if path matches a pattern of the list and
                 pattern as key for self.local_ratelimits.
        """
        for pattern in pattern_list:
            if uri.startswith(pattern[:-1]):
                return True, pattern
        return False, None

    def read_rate_limits_from_config(self, config_path):
        """
        Read rate limits from configuration file.

        :param config_path: path to the configuration file
        """
        config = common.load_config(config_path)
        rates = config.get('rates', {})
        self.global_ratelimits = rates.get('global', {})
        self.local_ratelimits = rates.get('default', {})
        self.buckets_ratelimits = rates.get('buckets', {})


class LimesRateLimitProvider(RateLimitProvider):
    """The provider to obtain rate limits from limes."""

    def __init__(self, service_type, logger=log.Logger(__name__), **kwargs):
        super(LimesRateLimitProvider, self).__init__(service_type=service_type, logger=logger, kwargs=kwargs)

        # Cache rate limits in redis if refresh_interval_seconds != 0
        self.__refresh_interval_seconds = kwargs.get('refresh_interval_seconds', 300)

        timeout = kwargs.get('redis_timeout', 2)
        self.__redis = pyredis.Pool(
            host=kwargs.get('redis_host', '127.0.0.1'),
            port=kwargs.get('redis_port', 6379),
            password=kwargs.get('redis_password'),
            conn_timeout=timeout,
            read_timeout=timeout,
            pool_size=kwargs.get('max_connections', 100),
            encoding='utf-8',
        )

        # For testing purposes.
        cli = kwargs.get('keystone_client', None)
        if cli:
            self.__keystone_client = cli
        else:
            self.__keystone_client = self.__authenticate(
                auth_url=kwargs.get('auth_url'),
                username=kwargs.get('username'),
                password=kwargs.get('password'),
                domain_name=kwargs.get('domain_name'),
                user_domain_name=kwargs.get('user_domain_name')
            )

        limes_api_uri = kwargs.get(common.Constants.limes_api_uri)
        if not limes_api_uri:
            limes_api_uri = self.__get_limes_base_url()
        self.__limes_base_url = limes_api_uri

    def get_global_rate_limits(self, action, target_type_uri, **kwargs):
        """
        Get the global rate limit per action and target type URI.
        Returns -1 if unlimited.

        :param action: the cadf action for the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters
        :return: the global rate limit or -1 if not set
        """
        # TODO: Global rate limits via Limes.
        return NOT_DEFINED_LIMIT

    def get_local_rate_limits(self, scope, action, target_type_uri, **kwargs):
        """
        Get the local (project/domain/ip, ..) rate limit per scope, action, target type URI.

        :param scope: the UUID of the project, domain or the IP
        :param action: the cadf action of the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters. should contain the domain id
        :return: the local rate limit or -1 if not set
        """
        domain_id = None
        if kwargs:
            domain_id = kwargs.get('domain_id')
        rate_limit_list = self.list_ratelimits_for_projects_in_domain(
            project_id=scope,
            domain_id=domain_id
        )

        # Find the current project by id.
        project = self.__find_project_by_id_in_list(scope, rate_limit_list.get('projects', []))
        # find the current service by type
        service = self.__find_service_by_type_in_list(self.service_type, project.get('services', []))
        # find the rates by target type URI
        rate = self.__find_rate_by_target_type_uri_and_action_in_list(target_type_uri, action, service.get('rates', []))
        # finally find the limit
        if 'limit' in rate and 'window' in rate:
            # convert Limes' rate limit format into the string format used by this middleware,
            # e.g. { 'limit': 10, 'window': '1m' } -> '10r/m'
            # e.g. { 'limit': 2, 'window': '10s' } -> '2r/10s'
            window = re.sub(r'^1([a-z])', r'\1', rate['window'])
            return "{0}r/{1}".format(rate['limit'], window)
        return NOT_DEFINED_LIMIT

    def __authenticate(self, auth_url, username, user_domain_name, password, domain_name):
        keystone_client = None
        try:
            self.logger.debug(
                'attempting authentication using with '
                'auth URL: {0}, username: {1}, user domain name: {2}, password: {3}, domain name: {4}'
                .format(auth_url, username, user_domain_name, '*' * len(password), domain_name)
            )

            auth = v3.Password(
                auth_url=auth_url,
                username=username,
                user_domain_name=user_domain_name,
                password=password,
                domain_name=domain_name,
                reauthenticate=True
            )
            sess = session.Session(auth=auth)
            keystone_client = keystonev3.Client(session=sess)
            self.logger.debug('successfully created keystone client and obtained token')

        except Exception as e:
            self.logger.error('failed to create keystone client: {0}'.format(str(e)))

        finally:
            return keystone_client

    def __get_limes_base_url(self, interface='public'):
        """
        Get Limes endpoint from service catalog.

        :param interface: the interface of the endpoint
        :return: the limes endpoint
        """
        limes_base_url = ''
        try:
            limes_service_id = None

            # Get list of services from keystone.
            service_list = self.__keystone_client.services.list()
            if not service_list:
                return

            # Find Limes service by name in service catalog.
            for service in service_list:
                if service.name == common.Constants.limes_service_type:
                    limes_service_id = service.id

            # Get Limes endpoint.
            endpoint_list = self.__keystone_client.endpoints.list()
            if not endpoint_list:
                return

            for endpoint in endpoint_list:
                if limes_service_id == endpoint.service_id and \
                        interface == endpoint.interface:
                    limes_base_url = endpoint.url
                    break

            self.logger.warning("could not find limes base url in endpoints")

        except Exception as e:
            self.logger.error("error looking up limes base url: {0}".format(str(e)))

        finally:
            return limes_base_url

    def list_ratelimits_for_projects_in_domain(self, project_id, domain_id=None):
        """
        Query limes for rate limits for projects in a domain.

        :param domain_id: the domain uid
        :param project_id: optional project uid
        :return: dictionary of projects and their rates in the given domain
        """
        path = '/v1'

        if not common.is_none_or_unknown(domain_id):
            path += '/domains/{0}'.format(domain_id)

        if not common.is_none_or_unknown(project_id):
            path += '/projects/{0}'.format(project_id)

        # List only rate limits and filter for the current service.
        params = {
            'service': self.service_type,
            'rates': 'only'
        }
        return self._get(path, params)

    def __find_project_by_id_in_list(self, project_id, project_list):
        return common.find_item_by_key_in_list(project_id, 'id', project_list)

    def __find_service_by_type_in_list(self, service_type, service_list):
        return common.find_item_by_key_in_list(service_type, 'type', service_list)

    def __find_rate_by_target_type_uri_and_action_in_list(self, target_type_uri, action, rate_list):
        rate_name = "{0}:{1}".format(target_type_uri, action)
        return common.find_item_by_key_in_list(rate_name, 'name', rate_list)

    def _get(self, path, params={}, headers={}):
        response_json = {}

        if not params:
            params = {}
        if not headers:
            headers = {}

        try:
            self.__limes_base_url = self.__limes_base_url or self.__get_limes_base_url()
            if not self.__limes_base_url:
                self.logger.error("limes base path is unknown. cannot get rate limits")
                return None

            # Set X-AUTH-TOKEN header.
            headers['X-AUTH-TOKEN'] = self.__keystone_client.session.get_token()

            resp_raw = requests.get(
                url=common.build_uri(self.__limes_base_url, path),
                params=params,
                headers=headers
            )
            response_json = resp_raw.json()
        except Exception as e:
            self.logger.error("error while getting rate limits from limes: {0}".format(str(e)))

        finally:
            return response_json
