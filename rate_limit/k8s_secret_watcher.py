# Copyright 2024 SAP SE
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

import base64
import threading
import time

import kubernetes
import kubernetes.client
import kubernetes.config
import kubernetes.watch

from . import log


class K8sSecretWatcher:
    """Watches a Kubernetes Secret and reloads Redis credentials on changes.

    Uses in-cluster service-account authentication. Call start() once during
    middleware init; it performs an initial synchronous read of the secret
    (so credentials are available before the first request), then starts a
    background daemon thread that streams changes.
    """

    def __init__(self, backend, secret_name, namespace, password_key='redis_password', username_key=None):
        self._backend = backend
        self._secret_name = secret_name
        self._namespace = namespace
        self._password_key = password_key
        self._username_key = username_key
        self._logger = log.Logger(__name__)

    def start(self):
        """Synchronously load credentials from the secret, then start background watch."""
        kubernetes.config.load_incluster_config()
        v1 = kubernetes.client.CoreV1Api()
        secret = v1.read_namespaced_secret(self._secret_name, self._namespace)
        self._load_from_secret(secret)
        t = threading.Thread(target=self._watch_loop, args=(v1,), daemon=True)
        t.start()

    def _decode(self, b64value):
        return base64.b64decode(b64value).decode('utf-8')

    def _load_from_secret(self, secret):
        data = secret.data or {}
        raw_password = data.get(self._password_key)
        if raw_password is None:
            self._logger.error(
                "key '{0}' not found in secret '{1}'".format(self._password_key, self._secret_name)
            )
            return
        password = self._decode(raw_password)
        username = None
        if self._username_key:
            raw_username = data.get(self._username_key)
            if raw_username is not None:
                username = self._decode(raw_username)
        self._backend.reload(password=password, username=username)
        ok, msg = self._backend.is_available()
        if ok:
            self._logger.info(
                "redis credentials reloaded from secret '{0}'".format(self._secret_name)
            )
        else:
            self._logger.warning(
                "redis credentials reloaded from secret '{0}' but backend is unavailable: {1}".format(
                    self._secret_name, msg
                )
            )

    def _watch_loop(self, v1):
        w = kubernetes.watch.Watch()
        backoff = 1
        while True:
            try:
                for event in w.stream(
                    v1.list_namespaced_secret,
                    namespace=self._namespace,
                    field_selector='metadata.name={0}'.format(self._secret_name),
                    timeout_seconds=0,
                ):
                    event_type = event['type']
                    if event_type in ('ADDED', 'MODIFIED'):
                        self._load_from_secret(event['object'])
                backoff = 1
            except Exception as e:
                self._logger.error(
                    "error watching secret '{0}': {1}; retrying in {2}s".format(
                        self._secret_name, e, backoff
                    )
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
