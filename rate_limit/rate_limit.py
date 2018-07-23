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
import os
import yaml

from datadog.dogstatsd import DogStatsd
from oslo_log import log
from oslo_config import cfg

from . import common
from . import errors
from . import limes
from . import response
from . import strategy as ratelimitstrategy


class OpenStackRateLimitMiddleware(object):
    """
    OpenStack Rate Limit Middleware

    Enforces configurable rate limits
    per service (compute, identity, object-store, ..),
    per scope (project uid, account, container),
    per resource (server, authentication, object, ..),
    per action (create, read, update, delete, authenticate, ..)
    """
    def __init__(self, app, wsgi_config, logger=log.getLogger(__name__), memcached=None):
        log.register_options(cfg.CONF)
        log.setup(cfg.CONF, 'openstack_rate_limit_middleware')
        self.logger = logger
        self.app = app
        # configuration via paste.ini
        self.wsgi_config = wsgi_config

        statsd_host = wsgi_config.get('statsd_host', '127.0.0.1')
        statsd_port = wsgi_config.get('statsd_port', 9125)
        statsd_prefix = wsgi_config.get('statsd_prefix', 'openstack_ratelimit')

        if memcached:
            self.memcached = memcached
        else:
            memcached_host = wsgi_config.get('memcached_host', '127.0.0.1')
            self.logger.debug('using memcached at {0}'.format(memcached_host))
            self.memcached = memcache.Client(
                servers=[memcached_host],
                debug=1
            )

        # statsd client
        self.metricsClient = DogStatsd(
            host=os.getenv('STATSD_HOST', statsd_host),
            port=int(os.getenv('STATSD_PORT', statsd_port)),
            namespace=os.getenv('STATSD_PREFIX', statsd_prefix)
        )

        # configuration via configuration file
        self.config = {}
        config_file = wsgi_config.get('config_file', None)
        if config_file:
            self.config = load_config(config_file)

        self.rate_limits = self.config.get(common.Constants.rate_limits, {})

        # get rate limits from config file or limes
        self.limes_enabled = wsgi_config.get('limes_enabled', False)
        self.limes_rate_limits = {}
        if self.limes_enabled and wsgi_config.get('auth_url'):
            self.limes = limes.Limes(logger=self.logger)
            self.limes.authenticate(
                auth_url=wsgi_config.get('auth_url'),
                username=wsgi_config.get('username'),
                user_domain_name=wsgi_config.get('user_domain_name'),
                password=wsgi_config.get('password'),
                domain_name=wsgi_config.get('domain_name')
            )
            # TODO: repeat every n minutes
            self.limes_rate_limits = self.limes.list_ratelimits_for_projects_in_domain(
                domain_id=wsgi_config.get('domain_id'),
                service=wsgi_config.get('service_type')
            )

        # use configured parameters or ensure defaults
        self.max_sleep_time_seconds = self.wsgi_config.get(common.Constants.max_sleep_time_seconds, 20)
        self.rate_buffer_seconds = self.wsgi_config.get(common.Constants.rate_buffer_seconds, 5)
        clock_accuracy = self.wsgi_config.get(common.Constants.clock_accuracy, '1ms')
        self.clock_accuracy = 1 / common.Units.parse(clock_accuracy)

        # setup ratelimit and blacklist response
        self._setup_response()

        # white-/blacklist can contain project, domain, user ids or the client ip address
        self.whitelist = self.config.get('whitelist', [])
        self.blacklist = self.config.get('blacklist', [])

        # configurable rate limit by
        self.rate_limit_by = self.wsgi_config.get('rate_limit_by', common.Constants.initiator_project_id)

    @classmethod
    def factory(cls, global_config, **local_config):
        conf = global_config.copy()
        conf.update(local_config)

        def limiter(app):
            return cls(app, conf)
        return limiter

    def __call__(self, environ, start_response):
        """
        WSGI entry point. Wraps environ in webob.Request

        :param environ: the WSGI environment dict
        :param start_response: WSGI callable
        """

        resp = self.app

        try:
            self.metricsClient.open_buffer()

            # get openstack-watcher-middleware classification from requests environ
            action, target_type_uri, scope = self.get_action_targettypeuri_scope_from_environ(environ)
            if not action or not target_type_uri or not scope:
                self.logger.warning(
                    "request cannot be handled by rate limit middleware due to missing attributes: "
                    "action: {0}, target_type_uri: {1}, scope: {2}".format(action, target_type_uri, scope)
                )
                return

            # check whitelist. if whitelisted break here
            if self.is_scope_whitelisted(scope):
                self.logger.info("{0} is whitelisted".format(scope))
                return

            # check blacklist. if blacklisted return BlacklistResponse
            if self.is_scope_blacklisted(scope):
                self.logger.info("{0} is blacklisted".format(scope))
                resp = self.blacklist_response
                return

            # check limes first for rate limits
            rate_limit, rate_strategy = None
            if self.limes_enabled:
                rate_limit, rate_strategy = self._get_rate_limit_and_strategy_from_limes(
                    action,
                    target_type_uri,
                    scope
                )

            # check whether a config file exists or a rate limit is set via limes
            if not self.rate_limits and not rate_limit:
                self.logger.debug("no rate limits configured")
                return

            # try to get rate limit from configuration file
            if not rate_limit:
                # check if there's a rate limit and strategy configured for the request,
                # which is identified by action, target_type_uri
                rate_limit, rate_strategy = self._get_rate_limit_and_strategy(action, target_type_uri)

            # still no rate limit? abort!
            if not rate_limit:
                self.logger.debug('no rate limit configured for request with '
                                  'action: {0}, target_type_uri: {1}'.format(action, target_type_uri))
                return

            # choose strategy
            if rate_strategy == 'slidingwindow':
                self.logger.debug("choosing sliding window strategy for '{0} {1}'".format(action, target_type_uri))
                strategy = ratelimitstrategy.SlidingWindowStrategy(
                    logger=self.logger,
                    memcached=self.memcached,
                    clock_accuracy=self.clock_accuracy,
                    rate_limit_response=self.ratelimit_response
                )
            else:
                self.logger.debug("choosing fixed window strategy for '{0} {1}'".format(action, target_type_uri))
                strategy = ratelimitstrategy.FixedWindowStrategy(
                    logger=self.logger,
                    memcached=self.memcached,
                    max_sleep_time_seconds=self.max_sleep_time_seconds,
                    rate_buffer_seconds=self.rate_buffer_seconds,
                    clock_accuracy=self.clock_accuracy,
                    rate_limit_response=self.ratelimit_response
                )

            # check if rate limit is reached
            rate_limit_response = strategy.rate_limit(scope, action, target_type_uri, rate_limit)
            if rate_limit_response:
                resp = rate_limit_response

            self.metricsClient.close_buffer()

        except Exception as e:
            self.logger.warning("checking rate limits failed with %s" % str(e))
        finally:
            return resp(environ, start_response)

    def is_scope_blacklisted(self, key_to_check):
        """
        check whether a scope (user_id, project_id or client ip) is blacklisted

        :param key_to_check: the user, project uid or client ip
        :return: bool whether the key is blacklisted
        """
        for entry in self.blacklist:
            if entry == key_to_check:
                return True
        return False

    def is_scope_whitelisted(self, key_to_check):
        """
        check whether a scope (user_id, project_id or client ip) is whitelisted

        :param key_to_check: the user, project uid or client ip
        :return: bool whether the key is whitelisted
        """
        for entry in self.whitelist:
            if entry == key_to_check:
                return True
        return False

    def get_action_targettypeuri_scope_from_environ(self, environ):
        action = target_type_uri = scope = None
        try:
            # get cadf action
            env_action = environ.get('WATCHER.ACTION')
            if env_action and env_action != common.Constants.unknown:
                action = env_action

            # get target type uri
            env_target_type_uri = environ.get('WATCHER.TARGET_TYPE_URI')
            if env_target_type_uri and env_target_type_uri != common.Constants.unknown:
                target_type_uri = env_target_type_uri

            # get cadf service name and trim from target_type_uri
            cadf_service_name = self._get_cadf_service_name(environ)
            if cadf_service_name and cadf_service_name != common.Constants.unknown:
                target_type_uri = self._trim_cadf_service_prefix_from_target_type_uri(
                    cadf_service_name, target_type_uri
                )

            # get scope, which might be initiator.project_id, target.project_id, etc.
            scope = self._get_scope_from_environ(environ)

        finally:
            self.logger.debug(
                'got WATCHTER.* attributes from environ: action: {0}, target_type_uri: {1}, scope: {2}'
                .format(action, target_type_uri, scope))
            return action, target_type_uri, scope

    def _get_scope_from_environ(self, environ):
        scope = env_scope = None
        try:
            if self.rate_limit_by == common.Constants.target_project_id:
                env_scope = environ.get('WATCHER.TARGET_PROJECT_ID', None)
            elif self.rate_limit_by == common.Constants.initiator_project_id:
                env_scope = environ.get('WATCHER.INITIATOR_PROJECT_ID', None)
            elif self.rate_limit_by == common.Constants.initiator_host_address:
                env_scope = environ.get('WATCHER.INITIATOR_HOST_ADDRESS')
            # make sure the scope is not 'unknown'
            if env_scope and env_scope != common.Constants.unknown:
                scope = env_scope
        finally:
            return scope

    def _get_cadf_service_name(self, environ):
        # try configured cadf service name
        svc_name = self.wsgi_config.get('cadf_service_name', None)
        if svc_name:
            return svc_name

        # try to extract from environ
        return environ.get('WATCHER.CADF_SERVICE_NAME', None)

    def _trim_cadf_service_prefix_from_target_type_uri(self, prefix, target_type_uri):
        """
        get cadf service name and trim from target_type_uri

        example:
            target_type_uri:      service/storage/object/account/container/object
            cadf_service_name:    service/storage/object
            => account/container/object

        :param prefix: the cadf service name prefixing the target_type_uri
        :param target_type_uri: the target_type_uri with the prefix
        :return: target_type_uri without prefix
        """
        target_type_uri_without_prefix = target_type_uri
        try:
            without_prefix = target_type_uri.split(prefix)
            if len(without_prefix) != 2:
                raise IndexError
            target_type_uri_without_prefix = without_prefix[-1].lstrip('/')
        except IndexError as e:
            self.logger.warning(
                "rate limiting might not be possible. cannot trim prefix '{0}' from target_type_uri '{1}': {2}"
                .format(prefix, target_type_uri, str(e))
            )
        finally:
            return target_type_uri_without_prefix

    def _get_rate_limit_and_strategy(self, action, target_type_uri):
        rate_limit = rate_strat = None
        try:
            rate_list = self.rate_limits.get(target_type_uri, None)
            if not rate_list:
                return None, None

            for rate in rate_list:
                rate_action = rate.get('action')
                rate_limit = rate.get('limit')
                rate_strat = rate.get('strategy')
                if rate_action and rate_action == action and \
                   rate_limit and rate_strat:
                    return rate_limit, rate_strat
        finally:
            return rate_limit, rate_strat

    def _setup_response(self):
        """
        setup RateLimitExceededResponse and BlacklistResponse
        """

        # default responses
        ratelimit_response = response.RateLimitExceededResponse()
        blacklist_response = response.BlacklistResponse()

        # overwrite default responses if custom ones are configured
        try:
            ratelimit_response_config = self.config.get(common.Constants.ratelimit_response)
            if ratelimit_response_config:
                status, headers, content_type, body, json_body = \
                    response.response_parameters_from_config(ratelimit_response_config)
                if headers and status and (body or json_body):
                    ratelimit_response = response.RateLimitExceededResponse(status, headers, content_type, body, json_body)

            blacklist_response_config = self.config.get(common.Constants.blacklist_response)
            if blacklist_response_config:
                status, headers, content_type, body, json_body = \
                    response.response_parameters_from_config(blacklist_response_config)
                if headers and status and (body or json_body):
                    blacklist_response = response.BlacklistResponse(status, headers, content_type, body, json_body)

        finally:
            self.ratelimit_response = ratelimit_response
            self.blacklist_response = blacklist_response

    def _get_rate_limit_and_strategy_from_limes(self, action, target_type_uri, scope):
        rate_limit = rate_strat = None
        try:
            if not self.limes_rate_limits:
                return

            project_list = self.limes_rate_limits.get('projects')
            service_list = self._find_service_in_project_list(project_list, 'project_id')
            rate_list = self._find_rate_in_service_list(service_list, self.service_type)
            action_list = self._find_action_in_rate_list(rate_list, target_type_uri)
            rate_limit, rate_strat = self._find_limit_and_strategy_in_action_list(action_list, action)

        finally:
            return rate_limit, rate_strat

    def _find_service_in_project_list(self, project_list, project_id):
        for project in project_list:
            if project.get('id') == project_id:
                return project.get('services', [])
        return []

    def _find_rate_in_service_list(self, service_list, service_type):
        for service in service_list:
            if service.get('type') == service_type:
                return service.get('rates', [])
        return []

    def _find_action_in_rate_list(self, rate_list, target_type_uri):
        for rate in rate_list:
            if rate.get('target_type_uri') == target_type_uri:
                return rate.get('actions', [])
        return []

    def _find_limit_and_strategy_in_action_list(self, action_list, action_name):
        for action in action_list:
            if action.get('name') == action_name:
                return action.get('limit'), action.get('strategy')
        return None, None


def load_config(cfg_file):
    yaml_conf = {}
    try:
        with open(cfg_file, 'r') as f:
            yaml_conf = yaml.safe_load(f)
    except IOError as e:
        raise errors.ConfigError("Failed to load configuration from file %s: %s" % (cfg_file, str(e)))
    finally:
        return yaml_conf
