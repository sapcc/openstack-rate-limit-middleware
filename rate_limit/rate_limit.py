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

import os

from datadog.dogstatsd import DogStatsd
from oslo_log import log
from oslo_config import cfg

from . import common
from . import provider
from . import response
from . import strategy as ratelimitstrategy

from .units import Units


class OpenStackRateLimitMiddleware(object):
    """
    OpenStack Rate Limit Middleware enforces configurable rate limits
    per service         ( compute, identity, object-store, .. )
    per scope           ( initiator|target project uid, initiator host address )
    per target_type_uri ( service/compute/servers, service/storage/block/volumes,.. )
    per action          ( create, read, update, delete, authenticate, .. )
    """

    def __init__(self, app, wsgi_config, logger=log.getLogger(__name__), memcached=None):
        log.register_options(cfg.CONF)
        log.setup(cfg.CONF, 'openstack_ratelimit_middleware')
        self.logger = logger
        self.app = app
        # configuration via paste.ini
        self.wsgi_config = wsgi_config

        # statsd used for metrics
        statsd_host = wsgi_config.get('statsd_host', '127.0.0.1')
        statsd_port = wsgi_config.get('statsd_port', 9125)
        statsd_prefix = wsgi_config.get('statsd_prefix', 'openstack_ratelimit')

        # init statsd client
        self.metricsClient = DogStatsd(
            host=os.getenv('STATSD_HOST', statsd_host),
            port=int(os.getenv('STATSD_PORT', statsd_port)),
            namespace=os.getenv('STATSD_PREFIX', statsd_prefix)
        )

        # memcache used to store count of requests, limes metrics, etc.
        memcache_host = wsgi_config.get('memcache_host', '127.0.0.1')
        self.logger.debug('using memcached at {0}'.format(memcache_host))

        # configuration via configuration file
        self.config = {}
        config_file = wsgi_config.get('config_file', None)
        if config_file:
            self.config = common.load_config(config_file)

        self.service_type = wsgi_config.get('service_type', None)
        self.cadf_service_name = wsgi_config.get('cadf_service_name', None)

        # use configured parameters or ensure defaults
        self.max_sleep_time_seconds = self.wsgi_config.get(common.Constants.max_sleep_time_seconds, 20)
        self.rate_buffer_seconds = self.wsgi_config.get(common.Constants.rate_buffer_seconds, 5)
        clock_accuracy = self.wsgi_config.get(common.Constants.clock_accuracy, '1ms')
        self.clock_accuracy = 1 / Units.parse(clock_accuracy)

        # setup ratelimit and blacklist response
        self._setup_response()

        # white-/blacklist can contain project, domain, user ids or the client ip address
        # don't apply rate limits to localhost
        default_whitelist = ['127.0.0.1', 'localhost']
        config_whitelist = self.config.get('whitelist', [])
        self.whitelist = default_whitelist + config_whitelist
        self.blacklist = self.config.get('blacklist', [])

        # configurable. rate limit by tuple of (rate_limit_by, action, target_type_uri)
        self.rate_limit_by = self.wsgi_config.get('rate_limit_by', common.Constants.initiator_project_id)

        # init strategy to enforce global rate limits
        self.global_ratelimits = ratelimitstrategy.SlidingWindowStrategy(
            logger=self.logger,
            memcache_host=memcache_host,
            clock_accuracy=self.clock_accuracy,
            rate_limit_response=self.ratelimit_response,
            memcached=memcached
        )

        # init strategy to enforce local (per ip, project, etc.) rate limits
        self.local_ratelimits = ratelimitstrategy.SlidingWindowStrategy(
            logger=self.logger,
            memcache_host=memcache_host,
            clock_accuracy=self.clock_accuracy,
            rate_limit_response=self.ratelimit_response,
            memcached=memcached
        )

        # init provider for rate limits. currently either from configuration or limes
        configuration_ratelimit_provider = provider.ConfigurationRateLimitProvider(
            service_type=self.service_type,
            logger=self.logger
        )
        configuration_ratelimit_provider.read_rate_limits_from_config(config_file)
        self.ratelimit_provider = configuration_ratelimit_provider

        # if limes is enabled and we want to rate limit by initiator|target project id,
        # set LimesRateLimitProvider as the provider for rate limits
        limes_enabled = wsgi_config.get('limes_enabled', False)
        if limes_enabled and common.is_ratelimit_by_project_id(self.rate_limit_by):
            try:
                limes_ratelimit_provider = provider.LimesRateLimitProvider(
                    service_type=self.service_type,
                    logger=self.logger,
                    memcache_host=memcache_host

                )
                limes_ratelimit_provider.authenticate(
                    auth_url=wsgi_config.get('auth_url'),
                    username=wsgi_config.get('username'),
                    user_domain_name=wsgi_config.get('user_domain_name'),
                    password=wsgi_config.get('password'),
                    domain_name=wsgi_config.get('domain_name')
                )

                limes_refresh_interval_seconds = wsgi_config.get(
                    'limes_refresh_interval_seconds', common.Constants.limes_refresh_interval_seconds
                )
                limes_ratelimit_provider.set_refresh_interval_seconds(limes_refresh_interval_seconds)
                self.ratelimit_provider = limes_ratelimit_provider
            except Exception as e:
                self.logger.debug("failed to setup limes rate limit provider: {0}".format(str(e)))

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
                    ratelimit_response = response.RateLimitExceededResponse(
                        status, headers, content_type, body, json_body
                    )

            blacklist_response_config = self.config.get(common.Constants.blacklist_response)
            if blacklist_response_config:
                status, headers, content_type, body, json_body = \
                    response.response_parameters_from_config(blacklist_response_config)
                if headers and status and (body or json_body):
                    blacklist_response = response.BlacklistResponse(status, headers, content_type, body, json_body)

        finally:
            self.ratelimit_response = ratelimit_response
            self.blacklist_response = blacklist_response

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

        # save the app's response so it can easily be returned
        resp = self.app

        try:
            self.metricsClient.open_buffer()

            # if the service type and/or service name is not configured,
            # attempt to extract watcher classification from environ and set it
            self._set_service_type_and_name(environ)

            # get openstack-watcher-middleware classification from requests environ
            scope, action, target_type_uri = self.get_scope_action_target_type_uri_from_environ(environ)

            metric_labels = [
                'service:{0}'.format(self.service_type),
                'service_name:{0}'.format(self.cadf_service_name),
                'action:{0}'.format(action),
                'scope:{0}'.format(scope),
                'target_type_uri:{0}'.format(target_type_uri)
            ]

            # don't rate limit if any of scope, action, target type URI is unknown
            if common.is_none_or_unknown(scope) or \
               common.is_none_or_unknown(action) or \
               common.is_none_or_unknown(target_type_uri):
                self.logger.debug(
                    "request cannot be handled by rate limit middleware due to missing attributes: "
                    "action: {0}, target_type_uri: {1}, scope: {2}".format(action, target_type_uri, scope)
                )
                self.metricsClient.increment('requests_unknown_classification_total', tags=metric_labels)
                return

            # check whitelist. if scope is whitelisted break here
            if self.is_scope_whitelisted(scope):
                self.logger.debug("{0} is whitelisted. skipping rate limit".format(scope))
                self.metricsClient.increment('requests_whitelisted_total', tags=metric_labels)
                return

            # check blacklist. if scope is blacklisted return BlacklistResponse
            if self.is_scope_blacklisted(scope):
                self.logger.debug("{0} is blacklisted. returning BlacklistResponse".format(scope))
                self.metricsClient.increment('requests_blacklisted_total', tags=metric_labels)
                resp = self.blacklist_response
                return

            # get global rate limits from the provider
            global_rate_limit, global_rate_strategy = self.ratelimit_provider.get_global_rate_limits(
                action, target_type_uri
            )
            # don't rate limit for rate_limit=-1 or if unknown
            if common.is_unlimited(global_rate_limit) or not global_rate_strategy:
                self.logger.debug("no global rate limits configured  or unlimited for request: '{0} {1}'".format(
                    action, target_type_uri)
                )
                return
            # check global rate limits
            rate_limit_response = self.global_ratelimits.rate_limit(
                scope, action, target_type_uri, global_rate_limit
            )
            if rate_limit_response:
                resp = rate_limit_response
                self.metricsClient.increment('requests_global_ratelimit_total', tags=metric_labels)
                return

            # get local (for a certain scope) rate limits from provider
            local_rate_limit, local_rate_strategy = self.ratelimit_provider.get_local_rate_limits(
                scope, action, target_type_uri
            )
            # don't rate limit for rate_limit=-1 or if unknown
            if common.is_unlimited(local_rate_limit) or not local_rate_strategy:
                self.logger.debug(
                    "no local rate limits configured or unlimited for request '{0} {1}' in scope '{3}'".format(
                        action, target_type_uri, scope
                    )
                )
                return

            # check local rate limits
            rate_limit_response = self.local_ratelimits.rate_limit(
                scope, action, target_type_uri, local_rate_limit
            )
            if rate_limit_response:
                resp = rate_limit_response
                self.metricsClient.increment('requests_local_ratelimit_total', tags=metric_labels)
                return

            self.metricsClient.close_buffer()

        except Exception as e:
            # TODO: debug
            self.logger.info("checking rate limits failed with: {0}".format(str(e)))

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

    def get_scope_action_target_type_uri_from_environ(self, environ):
        action = target_type_uri = scope = None
        try:
            # get cadf action
            env_action = environ.get('WATCHER.ACTION')
            if not common.is_none_or_unknown(env_action):
                action = env_action

            # get target type uri
            env_target_type_uri = environ.get('WATCHER.TARGET_TYPE_URI')
            if not common.is_none_or_unknown(env_target_type_uri):
                target_type_uri = env_target_type_uri

            # get cadf service name and trim from target_type_uri
            if not common.is_none_or_unknown(self.cadf_service_name):
                target_type_uri = self._trim_cadf_service_prefix_from_target_type_uri(
                    self.cadf_service_name, target_type_uri
                )

            # get scope, which might be initiator.project_id, target.project_id, etc.
            scope = self._get_scope_from_environ(environ)

        finally:
            self.logger.debug(
                'got WATCHER.* attributes from environ: action: {0}, target_type_uri: {1}, scope: {2}'
                .format(action, target_type_uri, scope))
            return scope, action, target_type_uri

    def _get_scope_from_environ(self, environ):
        """
        get the scope from the requests environ.
        the scope is configurable and may be the target|initiator project uid or the initiator host address

        :param environ: the requests environ
        :return: the scope
        """
        scope = env_scope = None
        if self.rate_limit_by == common.Constants.target_project_id:
            env_scope = environ.get('WATCHER.TARGET_PROJECT_ID', None)
        elif self.rate_limit_by == common.Constants.initiator_host_address:
            env_scope = environ.get('WATCHER.INITIATOR_HOST_ADDRESS', None)
        else:
            env_scope = environ.get('WATCHER.INITIATOR_PROJECT_ID', None)
        # make sure the scope is not 'unknown'
        if not common.is_none_or_unknown(env_scope):
            scope = env_scope
        return scope

    def _set_service_type_and_name(self, environ):
        """
        set the service type and name according to the watchers classification passed in the request WSGI environ
        if nothing was configured

        :param environ: the request WSGI environment
        """
        # get service type from environ
        if common.is_none_or_unknown(self.service_type):
            svc_type = environ.get('WATCHER.SERVICE_TYPE')
            if not common.is_none_or_unknown(svc_type):
                self.service_type = svc_type
                self.ratelimit_provider.service_type = self.service_type

        # set service name from environ
        if common.is_none_or_unknown(self.cadf_service_name):
            svc_name = environ.get('WATCHER.CADF_SERVICE_NAME')
            if not common.is_none_or_unknown(svc_name):
                self.cadf_service_name = svc_name
                self.ratelimit_provider.cadf_service_name = self.cadf_service_name

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
