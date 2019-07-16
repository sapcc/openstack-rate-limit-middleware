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


import keystoneclient.v3 as keystonev3
import redis
import requests

from keystoneauth1.identity import v3
from keystoneauth1 import session

from . import common
from . import log
from . import limes_types


class RateLimitProvider(object):
    """Interface to obtain rate limits from different sources."""

    def __init__(self, service_type, logger=log.Logger(__name__), **kwargs):
        self.service_type = service_type
        self.logger = logger
        # Global rate limits counted across all scopes.
        self.global_ratelimits = {}
        # Local rate limits counted per scope.
        self.local_ratelimits = {}

    def get_global_rate_limits(self, action, target_type_uri, **kwargs):
        """
        Get the global rate limit per action and target type URI.
        Returns -1 if unlimited.

        :param action: the CADF action for the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters
        :return: the global rate limit or -1 if not set
        """
        return -1

    def get_local_rate_limits(self, scope, action, target_type_uri, **kwargs):
        """
        Get the local (project/domain/ip, ..) rate limit per scope, action, target type URI.

        :param scope: the UUID of the project, domain or the IP
        :param action: the CADF action of the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters
        :return: the local rate limit or -1 if not set
        """
        return -1


class ConfigurationRateLimitProvider(RateLimitProvider):
    """The provider to obtain rate limits from a configuration file."""

    def __init__(self, service_type, logger=log.Logger(__name__), **kwargs):
        super(ConfigurationRateLimitProvider, self).__init__(
            service_type=service_type, logger=logger, kwargs=kwargs
        )

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
        for rl in ttu_ratelimits:
            ratelimit = rl.get('limit', None)
            if action == rl.get('action') and ratelimit:
                return ratelimit
        return -1

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
        for rl in ttu_ratelimits:
            ratelimit = rl.get('limit', None)
            if action == rl.get('action') and ratelimit:
                return ratelimit
        return -1

    def read_rate_limits_from_config(self, config_path):
        """
        Read rate limits from configuration file.

        :param config_path: path to the configuration file
        """
        config = common.load_config(config_path)
        rates = config.get('rates', {})
        self.global_ratelimits = rates.get('global', {})
        self.local_ratelimits = rates.get('default', {})


class LimesRateLimitProvider(RateLimitProvider):
    """The provider to obtain rate limits from limes."""

    def __init__(self, service_type, logger=log.Logger(__name__), **kwargs):
        super(LimesRateLimitProvider, self).__init__(service_type=service_type, logger=logger, kwargs=kwargs)

        # Cache rate limits in redis if refresh_interval_seconds != 0
        self.__refresh_interval_seconds = kwargs.get(
            'refresh_interval_seconds', 300,
        )

        timeout = kwargs.get('redis_timeout', 20)
        # Use a thread-safe blocking connection pool.
        conn_pool = redis.BlockingConnectionPool(
            host=kwargs.get('redis_host', '127.0.0.1'),
            port=kwargs.get('redis_port', 6379),
            max_connections=kwargs.get('max_connections', 100),
            timeout=timeout
        )
        self.__redis = redis.StrictRedis(
            connection_pool=conn_pool, decode_responses=True,
            socket_timeout=timeout, socket_connect_timeout=timeout,
        )

        # For testing purposes.
        cli = kwargs.get('keystone_client', None)
        if cli:
            self.__keystone_client = cli
        else:
            self.__keystone_client = self.__authenticate(
                auth_url=kwargs.get('auth_url', ''),
                username=kwargs.get('username', ''),
                password=kwargs.get('password', ''),
                domain_name=kwargs.get('domain_name', ''),
                user_domain_name=kwargs.get('user_domain_name', '')
            )

        limes_api_uri = kwargs.get(common.Constants.limes_api_uri, None)
        if not limes_api_uri:
            limes_api_uri = self.__get_limes_base_url()
        self.__limes_base_url = limes_api_uri

        script_name = "redis_set_expire_multiple.lua"
        script = common.load_lua_script(script_name)
        if not script:
            self.logger.error(
                "error loading rate limit script: '{0}'".format(script_name)
            )
            return
        self.__redis_set_expire_multiple_script = script
        self.__redis_set_expire_multiple_script_sha = hashlib.sha1(script.encode('utf-8')).hexdigest()

    def get_global_rate_limits(self, action, target_type_uri, **kwargs):
        """
        Get the global rate limit per action and target type URI.
        Returns -1 if unlimited.

        :param action: the cadf action for the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters
        :return: the global rate limit or -1 if not set
        """
        # TODO: Limes global rate limits.
        return -1

    def get_local_rate_limits(self, scope, action, target_type_uri, **kwargs):
        """
        Get the local (project/domain/ip, ..) rate limit per scope, action, target type URI.

        :param scope: the UUID of the project, domain or the IP
        :param action: the cadf action of the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters. should contain the domain id
        :return: the local rate limit or -1 if not set
        """
        domain_id = kwargs.get('domain_id', None)
        key = common.key_func(scope=scope, action=action, target_type_uri=target_type_uri)
        rl = self._get_rate_limit_from_redis(key)
        # if not domain_id:
        #     self.logger.debug("no domain_id provided")
        #     return -1
        if not rl:
            limes_rate_limits = self.list_ratelimits_for_projects_in_domain(domain_id=domain_id)
            self._add_rate_limits_to_redis(limes_rate_limits)
            rl = limes_rate_limits.get_rate_limit(
                service_type=self.service_type,
                project_id=scope,
                target_type_uri=target_type_uri,
                action=action
            )
        return rl

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

    def list_ratelimits_for_projects_in_domain(self, domain_id):
        """
        Query limes for rate limits for projects in a domain.

        :param domain_id: the domain uid
        :param project_id: optional project uid
        :return: dictionary of projects and their rates in the given domain
        """
        # List only rate limits and filter for the current service.
        params = {
            'service': self.service_type,
            'rates': 'only'
        }
        return self._get(
            '/v1/domains/{0}'.format(domain_id),
            params
        )

    def _get(self, path, params={}, headers={}):
        limes_project_list = limes_types.LimesProjectList(projects=[])

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

            limes_project_list = limes_types.decode_limes_json(resp_raw.json())

        except Exception as e:
            self.logger.error("error while getting rate limits from limes: {0}".format(str(e)))

        finally:
            return limes_project_list

    def _add_rate_limits_to_redis(self, rate_limits):
        rate_limit_key_dict = rate_limits.to_key_rate_limit_dict(service_type=self.service_type)
        try:
            self.__redis.evalsha(
                self.__redis_set_expire_multiple_script_sha, 2,
                str(rate_limit_key_dict), self.__refresh_interval_seconds,
            )

        # If the script is not (yet) present submit to redis and evaluate it.
        except redis.exceptions.NoScriptError:
            self.__redis.eval(
                self.__redis_set_expire_multiple_script, 2,
                str(rate_limit_key_dict), self.__refresh_interval_seconds,
            )

        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError, redis.exceptions.ResponseError) as e:
            self.logger.debug(
                "error executing redis script: {0}".format(str(e))
            )

    def _get_rate_limit_from_redis(self, project_id):
        rl = None
        try:
            rl = self.__redis.get(project_id)
        except (redis.ResponseError, redis.TimeoutError, redis.ConnectionError) as e:
            self.logger.debug(
                "unable to cache rate limits in redis: {0}".format(str(e))
            )
        finally:
            return rl
