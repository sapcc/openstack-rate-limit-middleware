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

import os

from datadog.dogstatsd import DogStatsd
from oslo_log import log
from oslo_config import cfg

from . import backend as rate_limit_backend
from . import common
from . import provider
from . import response

from .units import Units


class OpenStackRateLimitMiddleware(object):
    """
    OpenStack Rate Limit Middleware enforces configurable rate limits per combination of
      service         ( compute, identity, object-store, .. )
      scope           ( initiator|target project uid, initiator host address )
      target_type_uri ( service/compute/servers, service/storage/block/volumes,.. )
      action          ( create, read, update, delete, authenticate, .. )
    """

    def __init__(self, app, wsgi_config, logger=log.getLogger(__name__)):
        log.register_options(cfg.CONF)
        log.setup(cfg.CONF, 'openstack_ratelimit_middleware')
        self.logger = logger
        self.app = app
        # Configuration via paste.ini.
        self.wsgi_config = wsgi_config

        # StatsD is used to emit metrics.
        statsd_host = wsgi_config.get('statsd_host', '127.0.0.1')
        statsd_port = wsgi_config.get('statsd_port', 9125)
        statsd_prefix = wsgi_config.get('statsd_prefix', 'openstack_ratelimit')

        # Init StatsD client.
        self.metricsClient = DogStatsd(
            host=os.getenv('STATSD_HOST', statsd_host),
            port=int(os.getenv('STATSD_PORT', statsd_port)),
            namespace=os.getenv('STATSD_PREFIX', statsd_prefix)
        )

        # Get backend configuration.
        # Backend is used to store count of requests.
        backend_type = wsgi_config.get('backend', 'redis')
        self.logger.debug('using backend: {0}'.format(backend_type))

        backend_host = wsgi_config.get('backend_host', '127.0.0.1')
        self.logger.debug('using backend host {0}'.format(backend_host))

        backend_port = wsgi_config.get('backend_port', '6379')
        self.logger.debug('using backend port {0}'.format(backend_port))

        # Load configuration file.
        self.config = {}
        config_file = wsgi_config.get('config_file', None)
        if config_file:
            self.config = common.load_config(config_file)

        self.service_type = wsgi_config.get('service_type', None)

        # This is required to trim the prefix from the target_type_uri.
        # Example:
        #   service_type      = identity
        #   cadf_service_name = data/security
        #   target_type_uri   = data/security/auth/tokens -> auth/tokens
        self.cadf_service_name = wsgi_config.get('cadf_service_name', None)
        if common.is_none_or_unknown(self.cadf_service_name):
            self.cadf_service_name = common.CADF_SERVICE_TYPE_PREFIX_MAP.get(self.service_type, None)

        # Use configured parameters or ensure defaults.
        self.max_sleep_time_seconds = self.wsgi_config.get(common.Constants.max_sleep_time_seconds, 20)
        self.rate_buffer_seconds = self.wsgi_config.get(common.Constants.rate_buffer_seconds, 5)
        clock_accuracy = self.wsgi_config.get(common.Constants.clock_accuracy, '1ms')
        self.clock_accuracy = 1 / Units.parse(clock_accuracy)

        # Setup ratelimit and blacklist response.
        self._setup_response()

        # White-/blacklist can contain project, domain, user ids or the client ip address.
        # Don't apply rate limits to localhost.
        default_whitelist = ['127.0.0.1', 'localhost']
        config_whitelist = self.config.get('whitelist', [])
        self.whitelist = default_whitelist + config_whitelist
        self.blacklist = self.config.get('blacklist', [])

        # Configurable scope in which a rate limit is applied. Defaults to initiator project id.
        # Rate limits are applied based on the tuple of (rate_limit_by, action, target_type_uri).
        self.rate_limit_by = self.wsgi_config.get('rate_limit_by', common.Constants.initiator_project_id)

        # Initializes the backend as configured. Defaults to redis.
        if backend_type == common.Constants.backend_memcache:
            self.backend = rate_limit_backend.MemcachedBackend(
                host=backend_host,
                port=backend_port,
                rate_limit_response=self.ratelimit_response,
                logger=self.logger
            )
        else:
            self.backend = rate_limit_backend.RedisBackend(
                host=backend_host,
                port=backend_port,
                rate_limit_response=self.ratelimit_response,
                logger=self.logger
            )

        # Provider for rate limits. Defaults to configuration file.
        # Also supports Limes.
        configuration_ratelimit_provider = provider.ConfigurationRateLimitProvider(
            service_type=self.service_type,
            logger=self.logger
        )
        configuration_ratelimit_provider.read_rate_limits_from_config(config_file)
        self.ratelimit_provider = configuration_ratelimit_provider

        # If limes is enabled and we want to rate limit by initiator|target project id,
        # Set LimesRateLimitProvider as the provider for rate limits.
        limes_enabled = wsgi_config.get('limes_enabled', False)
        if limes_enabled and common.is_ratelimit_by_project_id(self.rate_limit_by):
            try:
                limes_ratelimit_provider = provider.LimesRateLimitProvider(
                    service_type=self.service_type,
                    logger=self.logger
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
        Setup configurable RateLimitExceededResponse and BlacklistResponse.
        """

        # Default responses.
        ratelimit_response = response.RateLimitExceededResponse()
        blacklist_response = response.BlacklistResponse()

        # Overwrite default responses if custom ones are configured.
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

    def _rate_limit(self, scope, action, target_type_uri):
        metric_labels = [
            'service:{0}'.format(self.service_type),
            'service_name:{0}'.format(self.cadf_service_name),
            'action:{0}'.format(action),
            'scope:{0}'.format(scope),
            'target_type_uri:{0}'.format(target_type_uri)
        ]

        # Check whitelist. If scope is whitelisted break here and don't apply any rate limits.
        if self.is_scope_whitelisted(scope):
            self.logger.debug("{0} is whitelisted. skipping rate limit".format(scope))
            self.metricsClient.increment('requests_whitelisted_total', tags=metric_labels)
            return None

        # Check blacklist. If scope is blacklisted return BlacklistResponse.
        if self.is_scope_blacklisted(scope):
            self.logger.debug("{0} is blacklisted. returning BlacklistResponse".format(scope))
            self.metricsClient.increment('requests_blacklisted_total', tags=metric_labels)
            return self.blacklist_response

        # Get global rate limits from the provider.
        global_rate_limit = self.ratelimit_provider.get_global_rate_limits(
            action, target_type_uri
        )
        # Don't rate limit if limit=-1 or unknown.
        if common.is_unlimited(global_rate_limit):
            self.logger.debug(
                "no global rate limits configured or unlimited for request: '{0} {1}'"
                .format(action, target_type_uri)
            )
            return None

        # Check global rate limits.
        # Global rate limits enforce a backend protection by counting all requests independent of their scope.
        rate_limit_response = self.backend.rate_limit(
            scope=None, action=action, target_type_uri=target_type_uri, max_rate_string=global_rate_limit
        )
        if rate_limit_response:
            self.metricsClient.increment('requests_global_ratelimit_total', tags=metric_labels)
            return rate_limit_response

        # Get local (for a certain scope) rate limits from provider.
        local_rate_limit = self.ratelimit_provider.get_local_rate_limits(
            scope, action, target_type_uri
        )

        # Don't rate limit for rate_limit=-1 or if unknown.
        if common.is_unlimited(local_rate_limit):
            self.logger.debug(
                "no local rate limits configured or unlimited for request '{0} {1}' in scope '{3}'".format(
                    action, target_type_uri, scope
                )
            )
            return None

        # Check local (for a specific scope) rate limits.
        rate_limit_response = self.backend.rate_limit(
            scope=scope, action=action, target_type_uri=target_type_uri, max_rate_string=local_rate_limit
        )
        if rate_limit_response:
            self.metricsClient.increment('requests_local_ratelimit_total', tags=metric_labels)
            return rate_limit_response

        return None

    def __call__(self, environ, start_response):
        """
        WSGI entry point. Wraps environ in webob.Request.

        :param environ: the WSGI environment dict
        :param start_response: WSGI callable
        """

        # Save the app's response so it can be returned easily.
        resp = self.app

        try:
            self.metricsClient.open_buffer()

            # If the service type and/or service name is not configured,
            # attempt to extract watcher classification from environ and set it.
            self._set_service_type_and_name(environ)

            # Get openstack-watcher-middleware classification from requests environ.
            scope, action, target_type_uri = self.get_scope_action_target_type_uri_from_environ(environ)

            # Don't rate limit if any of scope, action, target type URI is unknown.
            if common.is_none_or_unknown(scope) or \
               common.is_none_or_unknown(action) or \
               common.is_none_or_unknown(target_type_uri):
                self.logger.debug(
                    "request cannot be handled by rate limit middleware due to missing attributes: "
                    "action: {0}, target_type_uri: {1}, scope: {2}".format(action, target_type_uri, scope)
                )
                return

            r = self._rate_limit(scope, action, target_type_uri)
            if r:
                resp = r

        except Exception as e:
            self.logger.debug("checking rate limits failed with: {0}".format(str(e)))

        finally:
            self.metricsClient.close_buffer()
            return resp(environ, start_response)

    def is_scope_blacklisted(self, key_to_check):
        """
        Check whether a scope (user_id, project_id or client ip) is blacklisted.

        :param key_to_check: the user, project uid or client ip
        :return: bool whether the key is blacklisted
        """
        for entry in self.blacklist:
            if entry == key_to_check:
                return True
        return False

    def is_scope_whitelisted(self, key_to_check):
        """
        Check whether a scope (user_id, project_id or client ip) is whitelisted.

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
            # Get the CADF action.
            env_action = environ.get('WATCHER.ACTION')
            if not common.is_none_or_unknown(env_action):
                action = env_action

            # Get the target type URI.
            env_target_type_uri = environ.get('WATCHER.TARGET_TYPE_URI')
            if not common.is_none_or_unknown(env_target_type_uri):
                target_type_uri = env_target_type_uri

            # Get CADF service name and trim from target_type_uri.
            if not common.is_none_or_unknown(self.cadf_service_name):
                target_type_uri = self._trim_cadf_service_prefix_from_target_type_uri(
                    self.cadf_service_name, target_type_uri
                )

            # Get scope, which might be initiator.project_id, target.project_id, etc. .
            scope = self._get_scope_from_environ(environ)

        finally:
            self.logger.debug(
                'got WATCHER.* attributes from environ: action: {0}, target_type_uri: {1}, scope: {2}'
                .format(action, target_type_uri, scope))
            return scope, action, target_type_uri

    def _get_scope_from_environ(self, environ):
        """
        Get the scope from the requests environ.
        The scope is configurable and may be the target|initiator project uid or the initiator host address.

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
        Set the service type and name according to the watchers classification passed in the request WSGI environ.
        Used if nothing was configured.

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
        Get cadf service name and trim from target_type_uri.

        Example:
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
