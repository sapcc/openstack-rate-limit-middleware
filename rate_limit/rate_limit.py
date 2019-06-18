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
import logging

from datadog.dogstatsd import DogStatsd

from . import backend as rate_limit_backend
from . import common
from . import errors
from . import provider
from . import response

logging.basicConfig(level=logging.ERROR, format='%(asctime)-15s %(message)s')


class OpenStackRateLimitMiddleware(object):
    """
    OpenStack Rate Limit Middleware enforces configurable rate limits.

    Per combination of:
      service         ( compute, identity, object-store, .. )
      scope           ( initiator|target project uid, initiator host address )
      target_type_uri ( service/compute/servers, service/storage/block/volumes,.. )
      action          ( create, read, update, delete, authenticate, .. )
    """

    def __init__(self, app, wsgi_config, logger=logging.getLogger(__name__)):
        self.logger = logger
        self.app = app
        # Configuration via paste.ini.
        self.wsgi_config = wsgi_config

        # StatsD is used to emit metrics.
        statsd_host = wsgi_config.get('statsd_host', '127.0.0.1')
        statsd_port = common.to_int(wsgi_config.get('statsd_port', 9125))
        statsd_prefix = wsgi_config.get('statsd_prefix', 'openstack_ratelimit')

        # Init StatsD client.
        self.metricsClient = DogStatsd(
            host=os.getenv('STATSD_HOST', statsd_host),
            port=int(os.getenv('STATSD_PORT', statsd_port)),
            namespace=os.getenv('STATSD_PREFIX', statsd_prefix)
        )

        # Get backend configuration.
        # Backend is used to store count of requests.
        self.backend_host = wsgi_config.get('backend_host', '127.0.0.1')
        self.backend_port = common.to_int(self.wsgi_config.get('backend_port'), 6379)
        self.logger.debug(
            "using backend '{0}' on '{1}:{2}'".format('redis', self.backend_host, self.backend_port)
        )
        backend_timeout_seconds = common.to_int(self.wsgi_config.get('backend_timeout_seconds'), 20)
        backend_max_connections = common.to_int(self.wsgi_config.get('backend_max_connections'), 100)

        # Load configuration file.
        self.config = {}
        config_file = wsgi_config.get('config_file', None)
        if config_file:
            try:
                self.config = common.load_config(config_file)
            except errors.ConfigError as e:
                self.logger.warning(
                    "error loading configuration: {0}".format(str(e))
                )

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
        max_sleep_time_seconds = common.to_int(self.wsgi_config.get(common.Constants.max_sleep_time_seconds), 20)
        log_sleep_time_seconds = common.to_int(self.wsgi_config.get(common.Constants.log_sleep_time_seconds), 10)

        # Setup ratelimit and blacklist response.
        self._setup_response()

        # White-/blacklist can contain project, domain, user ids or the client ip address.
        # Don't apply rate limits to localhost.
        default_whitelist = ['127.0.0.1', 'localhost']
        config_whitelist = self.config.get('whitelist', [])
        self.whitelist = default_whitelist + config_whitelist
        self.blacklist = self.config.get('blacklist', [])

        # Mapping of potentially multiple CADF actions to one action.
        self.rate_limit_groups = self.config.get('groups', {})

        # Configurable scope in which a rate limit is applied. Defaults to initiator project id.
        # Rate limits are applied based on the tuple of (rate_limit_by, action, target_type_uri).
        self.rate_limit_by = self.wsgi_config.get('rate_limit_by', common.Constants.initiator_project_id)

        self.backend = rate_limit_backend.RedisBackend(
            host=self.backend_host,
            port=self.backend_port,
            rate_limit_response=self.ratelimit_response,
            max_sleep_time_seconds=max_sleep_time_seconds,
            log_sleep_time_seconds=log_sleep_time_seconds,
            logger=self.logger,
            timeout_seconds=backend_timeout_seconds,
            max_connections=backend_max_connections,
        )

        # Test if the backend is ready.
        is_available, msg = self.backend.is_available()
        if not is_available:
            self.logger.warning("rate limit not possible. the backend is not available: {0}".format(msg))

        # Provider for rate limits. Defaults to configuration file.
        # Also supports Limes.
        configuration_ratelimit_provider = provider.ConfigurationRateLimitProvider(
            service_type=self.service_type, logger=self.logger
        )
        # Force load of rate limits from configuration file.
        configuration_ratelimit_provider.read_rate_limits_from_config(config_file)
        self.ratelimit_provider = configuration_ratelimit_provider

        # If limes is enabled and we want to rate limit by initiator|target project id,
        # Set LimesRateLimitProvider as the provider for rate limits.
        limes_enabled = wsgi_config.get('limes_enabled', False)
        if limes_enabled:
            self.__setup_limes_ratelimit_provider()

    def _setup_response(self):
        """Setup configurable RateLimitExceededResponse and BlacklistResponse."""
        # Default responses.
        ratelimit_response = response.RateLimitExceededResponse()
        blacklist_response = response.BlacklistResponse()

        # Overwrite default responses if custom ones are configured.
        try:
            ratelimit_response_config = self.config.get(common.Constants.ratelimit_response)
            if ratelimit_response_config:
                status, status_code, headers, body, json_body = \
                    response.response_parameters_from_config(ratelimit_response_config)

                # Only create custom response if all parameters are given.
                if status and status_code and (body or json_body):
                    ratelimit_response = response.RateLimitExceededResponse(
                        status=status, status_code=status_code, headerlist=headers, body=body, json_body=json_body
                    )

            blacklist_response_config = self.config.get(common.Constants.blacklist_response)
            if blacklist_response_config:
                status, status_code, headers, body, json_body = \
                    response.response_parameters_from_config(blacklist_response_config)

                # Only create custom response if all parameters are given.
                if status and status_code and (body or json_body):
                    blacklist_response = response.BlacklistResponse(
                        status=status, status_code=status_code, headerlist=headers, body=body, json_body=json_body
                    )

        except Exception as e:
            self.logger.debug(
                "error configuring custom responses. falling back to defaults: {0}".format(str(e))
            )

        finally:
            self.ratelimit_response = ratelimit_response
            self.blacklist_response = blacklist_response

    def __setup_limes_ratelimit_provider(self):
        """Setup Limes as provider for rate limits. If not successful fallback to configuration file."""
        try:
            limes_ratelimit_provider = provider.LimesRateLimitProvider(
                service_type=self.service_type,
                logger=self.logger,
                redis_host=self.backend_host,
                redis_port=self.backend_port,
                refresh_interval_seconds=self.wsgi_config.get(common.Constants.limes_refresh_interval_seconds, 300),
                limes_api_uri=self.wsgi_config.get(common.Constants.limes_api_uri),
                auth_url=self.wsgi_config.get('identity_auth_url'),
                username=self.wsgi_config.get('username'),
                user_domain_name=self.wsgi_config.get('user_domain_name'),
                password=self.wsgi_config.get('password'),
                domain_name=self.wsgi_config.get('domain_name')
            )
            self.ratelimit_provider = limes_ratelimit_provider

        except Exception as e:
            self.logger.debug("failed to setup limes rate limit provider: {0}".format(str(e)))

    @classmethod
    def factory(cls, global_config, **local_config):
        conf = global_config.copy()
        conf.update(local_config)

        def limiter(app):
            return cls(app, conf)
        return limiter

    def _rate_limit(self, scope, action, target_type_uri, **kwargs):
        """
        Check the whitelist, blacklist, global and local ratelimits.

        :param scope: the scope of the request
        :param action: the action of the request
        :param target_type_uri: the target type URI of the response
        :return: None or BlacklistResponse or RateLimitResponse
        """
        # Labels used for all metrics.
        metric_labels = [
            'service:{0}'.format(self.service_type),
            'service_name:{0}'.format(self.cadf_service_name),
            'action:{0}'.format(action),
            '{0}:{1}'.format(self.rate_limit_by, scope),
            'target_type_uri:{0}'.format(target_type_uri)
        ]

        # Check whether a set of CADF actions are accounted together.
        new_action = self.get_action_from_rate_limit_groups(action)
        if not common.is_none_or_unknown(new_action):
            action = new_action
            metric_labels.append(
                'action_group:{0}'.format(action)
            )

        # Get CADF service name and trim from target_type_uri.
        trimmed_target_type_uri = target_type_uri
        if not common.is_none_or_unknown(self.cadf_service_name):
            trimmed_target_type_uri = self._trim_cadf_service_prefix_from_target_type_uri(
                self.cadf_service_name, target_type_uri
            )

        # The key of the scope in the format $domainName/projectName.
        scope_name_key = kwargs.get('scope_name_key', None)

        # Check whitelist. If scope is whitelisted break here and don't apply any rate limits.
        if self.is_scope_whitelisted(scope) or self.is_scope_whitelisted(scope_name_key):
            self.logger.debug(
                "scope {0} (key: {1}) is whitelisted. skipping rate limit".format(scope, scope_name_key)
            )
            self.metricsClient.increment('requests_whitelisted_total', tags=metric_labels)
            return None

        # Check blacklist. If scope is blacklisted return BlacklistResponse.
        if self.is_scope_blacklisted(scope) or self.is_scope_blacklisted(scope_name_key):
            self.logger.debug(
                "scope {0} (key: {1}) is blacklisted. returning BlacklistResponse".format(scope, scope_name_key)
            )
            self.metricsClient.increment('requests_blacklisted_total', tags=metric_labels)
            return self.blacklist_response

        # Get global rate limits from the provider.
        global_rate_limit = self.ratelimit_provider.get_global_rate_limits(
            action, trimmed_target_type_uri
        )

        # Don't rate limit if limit=-1 or unknown.
        if not common.is_unlimited(global_rate_limit):
            self.logger.debug(
                "global rate limit configured for request with action '{0}', target type URI '{1}': '{2}'"
                .format(action, target_type_uri, global_rate_limit)
            )

            # Check global rate limits.
            # Global rate limits enforce a backend protection by counting all requests independent of their scope.
            rate_limit_response = self.backend.rate_limit(
                scope=None, action=action, target_type_uri=trimmed_target_type_uri, max_rate_string=global_rate_limit
            )
            if rate_limit_response:
                self.metricsClient.increment('requests_global_ratelimit_total', tags=metric_labels)
                return rate_limit_response

        # Get local (for a certain scope) rate limits from provider.
        local_rate_limit = self.ratelimit_provider.get_local_rate_limits(
            scope, action, trimmed_target_type_uri
        )

        # Don't rate limit for rate_limit=-1 or if unknown.
        if not common.is_unlimited(local_rate_limit):
            self.logger.debug(
                "local rate limit configured for request with action '{0}', target type URI '{1}', scope '{2}': '{3}'"
                .format(action, target_type_uri, scope, local_rate_limit)
            )

            # Check local (for a specific scope) rate limits.
            rate_limit_response = self.backend.rate_limit(
                scope=scope, action=action, target_type_uri=trimmed_target_type_uri, max_rate_string=local_rate_limit
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

            # Don't rate limit if any of scope, action, target type URI cannot be determined.
            if common.is_none_or_unknown(scope) or \
               common.is_none_or_unknown(action) or \
               common.is_none_or_unknown(target_type_uri):
                self.logger.debug(
                    "request cannot be handled by rate limit middleware due to missing attributes: "
                    "action: {0}, target_type_uri: {1}, scope: {2}".format(action, target_type_uri, scope)
                )
                self.metricsClient.increment(
                    'requests_unkown_classification',
                    tags=['service:{0}'.format(self.service_type), 'service_name:{0}'.format(self.cadf_service_name)]
                )
                return

            # Returns a RateLimitResponse or BlacklistResponse or None, in which case the original response is returned.
            rate_limit_response = self._rate_limit(
                scope=scope, action=action, target_type_uri=target_type_uri,
                scope_name_key=self._get_scope_name_key_from_environ(environ),
            )
            if rate_limit_response:
                rate_limit_response.set_environ(environ)
                resp = rate_limit_response

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
        """
        Get the scope, action, target type URI from the request environ.

        :param environ: the request environ
        :return: tuple of scope, action, target type URI
        """
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

            # Get scope from request environment, which might be an initiator.project_id, target.project_id, etc. .
            env_scope = self._get_scope_from_environ(environ)
            if not common.is_none_or_unknown(env_scope):
                scope = env_scope

        except Exception as e:
            self.logger.debug(
                "error while getting scope, action, target type URI from environ".format(str(e))
            )

        finally:
            self.logger.debug(
                'got WATCHER.* attributes from environ: action: {0}, target_type_uri: {1}, scope: {2}'
                .format(action, target_type_uri, scope))
            return scope, action, target_type_uri

    def _get_scope_from_environ(self, environ):
        """
        Get the scope from the requests environ.
        The scope is configurable and may be the target|initiator project uid or the initiator host address.
        Default to initiator project ID.

        :param environ: the requests environ
        :return: the scope
        """
        scope = None
        if self.rate_limit_by == common.Constants.target_project_id:
            env_scope = environ.get('WATCHER.TARGET_PROJECT_ID', None)
        elif self.rate_limit_by == common.Constants.initiator_host_address:
            env_scope = environ.get('WATCHER.INITIATOR_HOST_ADDRESS', None)
        else:
            env_scope = environ.get('WATCHER.INITIATOR_PROJECT_ID', None)

        # Ensure the scope is not 'unknown'.
        if not common.is_none_or_unknown(env_scope):
            scope = env_scope
        return scope

    def _get_scope_name_key_from_environ(self, environ):
        """
        Attempt to build the key '$domainName/$projectName' from the WATCHER attributes found in the request environ

        :param environ: the request environ
        :return: the key or None
        """
        _domain_name = environ.get('WATCHER.INIITATOR_PROJECT_DOMAIN_NAME', None)
        _project_domain_name = environ.get('WATCHER.INIITATOR_PROJECT_DOMAIN_NAME', None)
        project_name = environ.get('WATCHER.INITIATOR_PROJECT_NAME', None)
        domain_name = _project_domain_name or _domain_name

        if common.is_none_or_unknown(project_name) or common.is_none_or_unknown(domain_name):
            return None
        return '{0}/{1}'.format(domain_name, project_name)

    def _set_service_type_and_name(self, environ):
        """
        Set the service type and name according to the watchers classification passed in the request WSGI environ.
        Used if nothing was configured.

        :param environ: the request WSGI environment
        """
        # Get service type from request environ.
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
            target_type_uri:            service/storage/object/account/container/object
            cadf_service_name:          service/storage/object
            => trimmed_target_type_uri: account/container/object

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

    def get_action_from_rate_limit_groups(self, action):
        """
        Multiple CADF actions can be grouped and accounted as one entity.

        :param action: the original CADF action
        :return: the original action or action as per grouping
        """
        for group in self.rate_limit_groups:
            if action in self.rate_limit_groups[group]:
                return group
        return action
