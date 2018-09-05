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


import memcache
import requests

from oslo_log import log
from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client

from . import common


class RateLimitProvider(object):
    """
    Interface to obtain rate limits from different sources

    """
    def __init__(self, service_type, logger=log.getLogger(__name__), **kwargs):
        self.service_type = service_type
        self.logger = logger
        self.global_ratelimits = {}
        self.default_local_ratelimits = {}

    def get_global_rate_limits(self, action, target_type_uri, **kwargs):
        """
        get the global rate limit per action and target type URI
        returns -1 if unlimited

        :param action: the cadf action for the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters
        :return: the global rate limit or -1 if not set
        """
        raise NotImplementedError

    def get_local_rate_limits(self, scope, action, target_type_uri, **kwargs):
        """
        get the local (project/domain/ip, ..) rate limit per scope, action, target type URI

        :param scope: the UUID of the project, domain or the IP
        :param action: the cadf action of the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters
        :return: the local rate limit or -1 if not set
        """
        raise NotImplementedError


class ConfigurationRateLimitProvider(RateLimitProvider):
    """
    The provider to obtain rate limits from a configuration file

    """
    def __init__(self, service_type, logger=log.getLogger(__name__), **kwargs):
        super(ConfigurationRateLimitProvider, self).__init__(
            service_type=service_type, logger=logger, kwargs=kwargs
        )

    def get_global_rate_limits(self, action, target_type_uri, **kwargs):
        """
        get the global rate limit per action and target type URI
        returns -1 if unlimited

        :param action: the cadf action for the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters
        :return: the global rate limit or -1 if not set
        """
        ttu_ratelimits = self.global_ratelimits.get(target_type_uri, [])
        for rl in ttu_ratelimits:
            ratelimit = rl.get('limit', None)
            ratestrategy = rl.get('strategy', 'slidingwindow')
            if action == rl.get('action') and ratelimit:
                return ratelimit, ratestrategy
        return -1, 'slidingwindow'

    def get_local_rate_limits(self, scope, action, target_type_uri, **kwargs):
        """
        get the local (project/domain/ip, ..) rate limit per scope, action, target type URI

        :param scope: the UUID of the project, domain or the IP
        :param action: the cadf action of the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters
        :return: the local rate limit or -1 if not set
        """
        ttu_ratelimits = self.default_local_ratelimits.get(target_type_uri, [])
        for rl in ttu_ratelimits:
            ratelimit = rl.get('limit', None)
            ratestrategy = rl.get('strategy', 'slidingwindow')
            if action == rl.get('action') and ratelimit:
                return ratelimit, ratestrategy
        return -1, 'slidingwindow'

    def read_rate_limits_from_config(self, config_path):
        """
        read rate limits from configuration file

        :param config_path: path to the configuration file
        """
        config = common.load_config(config_path)
        rates = config.get('rates', {})
        self.global_ratelimits = rates.get('global', {})
        self.default_local_ratelimits = rates.get('default', {})


class LimesRateLimitProvider(RateLimitProvider):
    """
    The provider to obtain rate limits from limes
    """

    def __init__(self, service_type, logger=log.getLogger(__name__), **kwargs):
        super(LimesRateLimitProvider, self).__init__(
            service_type=service_type, logger=logger, kwargs=kwargs
        )

        # limes provider will use memcached to store ratelimits for a configurable time (refresh_interval_seconds)
        memcache_host = '127.0.0.1'
        if kwargs:
            memcache_host = kwargs.get('memcache_host', '127.0.0.1')

        self.memcached = memcache.Client(
            servers=[memcache_host],
            debug=1
        )

        # declare limes specifics
        self.keystone = None
        self.limes_base_url = None
        self.refresh_interval_seconds = common.Constants.limes_refresh_interval_seconds

    def get_global_rate_limits(self, action, target_type_uri, **kwargs):
        """
        get the global rate limit per action and target type URI
        returns -1 if unlimited

        :param action: the cadf action for the request
        :param target_type_uri: the target type URI of the request
        :param kwargs: optional, additional parameters
        :return: the global rate limit or -1 if not set
        """

        # TODO: global rate limits via configuration file or limes constraints?
        return -1, 'slidingwindow'

    def get_local_rate_limits(self, scope, action, target_type_uri, **kwargs):
        """
        get the local (project/domain/ip, ..) rate limit per scope, action, target type URI

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

        # find the current project by id
        project = self._find_project_by_id_in_list(scope, rate_limit_list.get('projects', []))
        # find the current service by type
        service = self._find_service_by_type_in_list(self.service_type, project.get('services', []))
        # find the rates by target type URI
        rate = self._find_rate_by_target_type_uri_in_list(target_type_uri, service.get('rates', []))
        # finally find the limit and strategy
        limit, strategy = self._find_limit_and_strategy_by_action_in_list(action, rate.get('actions', []))
        if limit and strategy:
            return limit, strategy
        # otherwise return -1 (unlimited)
        return -1, 'slidingwindow'

    def set_refresh_interval_seconds(self, refresh_interval_seconds):
        """
        set the interval in which rate limits are refreshed

        :param refresh_interval_seconds: the interval in seconds
        """
        self.refresh_interval_seconds = int(refresh_interval_seconds)

    def authenticate(self, auth_url, username, user_domain_name, password, domain_name):
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
            self.keystone = client.Client(session=sess)
            self.logger.debug('successfully created keystone client and obtained token')
        except Exception as e:
            self.logger.error('failed to create keystone client: {0}'.format(str(e)))

    def _get_limes_base_url(self, interface='public'):
        limes_base_url = ''
        try:
            limes_service_id = None

            service_list = self.keystone.services.list()
            if not service_list:
                return

            for service in service_list:
                if service.name == 'limes':
                    limes_service_id = service.id

            endpoint_list = self.keystone.endpoints.list()
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
            self.limes_base_url = limes_base_url

    def list_ratelimits_for_projects_in_domain(self, project_id, domain_id=None):
        """
        Query limes for rate limits for projects in a domain
        :param domain_id: the domain uid
        :param project_id: optional project uid
        :param action: optional cadf action
        :return: dictionary of projects and their rates in the given domain
        """
        path = '/v1'

        if not common.is_none_or_unknown(domain_id):
            path += '/domains/{0}'.format(domain_id)

        if not common.is_none_or_unknown(project_id):
            path += '/projects/{0}'.format(project_id)

        params = {
            'service': self.service_type
        }

        self.logger.debug("getting rate limits from limes: {0}".format(path))

        return self._get(path, params)

    def _get_rate_limit_and_strategy_from_limes_response(self, scope, action, target_type_uri, domain_id):
        rate_limit = rate_strat = None
        try:
            key = 'ratelimit_limes_{0}'.format(domain_id)
            limes_ratelimits = self.memcached.get(key)
            if not limes_ratelimits:
                # expired from memcached. get fresh from limes and store again.
                limes_ratelimits = self.limes.list_ratelimits_for_projects_in_domain(domain_id)
                self.memcached.set(
                    key=key, val=limes_ratelimits, time=self.limes_refresh_interval_seconds, noreply=True
                )

            # parse limes response
            project_list = limes_ratelimits.get('projects', [])
            service_list = self._find_service_in_project_list(project_list, scope)
            rate_list = self._find_rate_in_service_list(service_list, self.service_type)
            action_list = self._find_action_in_rate_list(rate_list, target_type_uri)
            rate_limit, rate_strat = self._find_limit_and_strategy_in_action_list(action_list, action)

        except Exception as e:
            self.logger.error(
                "could not extract limts for action '{0}', target_type_uri: '{1}', scope: '{2}' from limes: {3}"
                .format(action, target_type_uri, scope, str(e))
            )
        finally:
            return rate_limit, rate_strat

    def _find_project_by_id_in_list(self, project_id, project_list):
        return common.find_item_by_key_in_list(project_id, 'id', project_list)

    def _find_service_by_type_in_list(self, service_type, service_list):
        return common.find_item_by_key_in_list(service_type, 'type', service_list)

    def _find_rate_by_target_type_uri_in_list(self, target_type_uri, rate_list):
        return common.find_item_by_key_in_list(target_type_uri, 'targetTypeURI', rate_list)

    def _find_limit_and_strategy_by_action_in_list(self, action_name, action_list):
        action = common.find_item_by_key_in_list(
            action_name, 'name', action_list,
            {'limit': -1, 'strategy': 'slidingwindow'}
        )
        return action.get('limit'), action.get('strategy')

    def _get(self, path, params={}, headers={}):
        response_json = {}
        try:
            if not params:
                params = {}
            if not headers:
                headers = {}
            self.limes_base_url = self.limes_base_url or self._get_limes_base_url()
            if not self.limes_base_url:
                self.logger.error("limes base path is unknown. get not get rate limits")
                return None

            # only list rates
            params['rates'] = True

            # set X-AUTH-TOKEN header
            headers['X-AUTH-TOKEN'] = self.keystone.session.get_token()
            url = self.limes_base_url + path

            resp_raw = requests.get(url=url, params=params, headers=headers)
            response_json = resp_raw.json()
        except Exception as e:
            self.logger.error("error while getting rate limits from limes: {0}".format(str(e)))
        finally:
            return response_json
