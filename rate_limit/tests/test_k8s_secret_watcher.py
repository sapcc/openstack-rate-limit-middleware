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
import unittest
from unittest.mock import MagicMock, patch

from rate_limit.k8s_secret_watcher import K8sSecretWatcher


def _b64(s):
    return base64.b64encode(s.encode()).decode()


def _make_secret(data):
    """Build a mock V1Secret with the given plain-text data dict."""
    secret = MagicMock()
    secret.data = {k: _b64(v) for k, v in data.items()}
    return secret


class TestK8sSecretWatcherStart(unittest.TestCase):

    def setUp(self):
        self.backend = MagicMock()
        self.backend.is_available.return_value = (True, '')

    @patch('rate_limit.k8s_secret_watcher.kubernetes.config.load_incluster_config')
    @patch('rate_limit.k8s_secret_watcher.kubernetes.client.CoreV1Api')
    def test_start_reads_secret_and_calls_reload(self, mock_api_cls, mock_load_cfg):
        v1 = mock_api_cls.return_value
        v1.read_namespaced_secret.return_value = _make_secret({'redis_password': 'mypass'})
        with patch.object(K8sSecretWatcher, '_watch_loop'):
            w = K8sSecretWatcher(self.backend, 'redis-creds', 'kube-system')
            w.start()

        v1.read_namespaced_secret.assert_called_once_with('redis-creds', 'kube-system')
        self.backend.reload.assert_called_once_with(password='mypass', username=None)

    @patch('rate_limit.k8s_secret_watcher.kubernetes.config.load_incluster_config')
    @patch('rate_limit.k8s_secret_watcher.kubernetes.client.CoreV1Api')
    def test_start_passes_username_when_username_key_set(self, mock_api_cls, mock_load_cfg):
        v1 = mock_api_cls.return_value
        v1.read_namespaced_secret.return_value = _make_secret({'password': 'pass', 'username': 'alice'})
        with patch.object(K8sSecretWatcher, '_watch_loop'):
            w = K8sSecretWatcher(
                self.backend, 'redis-creds', 'kube-system',
                password_key='password', username_key='username',
            )
            w.start()

        self.backend.reload.assert_called_once_with(password='pass', username='alice')

    @patch('rate_limit.k8s_secret_watcher.kubernetes.config.load_incluster_config')
    @patch('rate_limit.k8s_secret_watcher.kubernetes.client.CoreV1Api')
    def test_start_logs_warning_when_backend_unavailable_after_reload(self, mock_api_cls, mock_load_cfg):
        v1 = mock_api_cls.return_value
        v1.read_namespaced_secret.return_value = _make_secret({'redis_password': 'wrongpass'})
        self.backend.is_available.return_value = (False, 'auth failed')
        with patch.object(K8sSecretWatcher, '_watch_loop'):
            w = K8sSecretWatcher(self.backend, 'redis-creds', 'kube-system')
            w.start()  # must not raise

        self.backend.reload.assert_called_once()

    @patch('rate_limit.k8s_secret_watcher.kubernetes.config.load_incluster_config')
    @patch('rate_limit.k8s_secret_watcher.kubernetes.client.CoreV1Api')
    def test_start_does_not_call_reload_when_password_key_missing(self, mock_api_cls, mock_load_cfg):
        v1 = mock_api_cls.return_value
        secret = MagicMock()
        secret.data = {}  # no password key
        v1.read_namespaced_secret.return_value = secret
        with patch.object(K8sSecretWatcher, '_watch_loop'):
            w = K8sSecretWatcher(self.backend, 'redis-creds', 'kube-system')
            w.start()  # must not raise

        self.backend.reload.assert_not_called()

    @patch('rate_limit.k8s_secret_watcher.kubernetes.config.load_incluster_config')
    @patch('rate_limit.k8s_secret_watcher.kubernetes.client.CoreV1Api')
    def test_start_launches_background_daemon_thread(self, mock_api_cls, mock_load_cfg):
        v1 = mock_api_cls.return_value
        v1.read_namespaced_secret.return_value = _make_secret({'password': 'p'})
        started = threading.Event()

        def fake_watch(v1_arg):
            started.set()
            time.sleep(10)

        with patch.object(K8sSecretWatcher, '_watch_loop', side_effect=fake_watch):
            w = K8sSecretWatcher(self.backend, 'redis-creds', 'kube-system')
            before = threading.active_count()
            w.start()
            started.wait(timeout=2)

        self.assertGreater(threading.active_count(), before)


class TestK8sSecretWatcherWatchLoop(unittest.TestCase):

    def setUp(self):
        self.backend = MagicMock()
        self.backend.is_available.return_value = (True, '')
        self.v1 = MagicMock()

    def _make_watcher(self, **kwargs):
        defaults = dict(backend=self.backend, secret_name='redis-creds', namespace='kube-system')
        defaults.update(kwargs)
        return K8sSecretWatcher(**defaults)

    def _run_watch_loop_once(self, watcher, events):
        mock_watch = MagicMock()
        call_count = [0]

        def make_stream(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return iter(events)
            raise Exception('test sentinel to exit loop')

        mock_watch.stream.side_effect = make_stream

        with patch('rate_limit.k8s_secret_watcher.kubernetes.watch.Watch', return_value=mock_watch), \
             patch('rate_limit.k8s_secret_watcher.time.sleep', side_effect=StopIteration):
            try:
                watcher._watch_loop(self.v1)
            except StopIteration:
                pass

    def test_modified_event_triggers_reload(self):
        w = self._make_watcher()
        events = [{'type': 'MODIFIED', 'object': _make_secret({'redis_password': 'newpass'})}]
        self._run_watch_loop_once(w, events)
        self.backend.reload.assert_called_once_with(password='newpass', username=None)

    def test_added_event_triggers_reload(self):
        w = self._make_watcher()
        events = [{'type': 'ADDED', 'object': _make_secret({'redis_password': 'initialpass'})}]
        self._run_watch_loop_once(w, events)
        self.backend.reload.assert_called_once_with(password='initialpass', username=None)

    def test_deleted_event_does_not_trigger_reload(self):
        w = self._make_watcher()
        events = [{'type': 'DELETED', 'object': _make_secret({'redis_password': 'pass'})}]
        self._run_watch_loop_once(w, events)
        self.backend.reload.assert_not_called()

    def test_watch_loop_retries_after_exception(self):
        w = self._make_watcher()

        def fake_stream(*args, **kwargs):
            raise Exception('network error')

        mock_watch = MagicMock()
        mock_watch.stream.side_effect = fake_stream
        sleep_calls = []

        def fake_sleep(n):
            sleep_calls.append(n)
            raise StopIteration

        with patch('rate_limit.k8s_secret_watcher.kubernetes.watch.Watch', return_value=mock_watch), \
             patch('rate_limit.k8s_secret_watcher.time.sleep', side_effect=fake_sleep):
            try:
                w._watch_loop(self.v1)
            except StopIteration:
                pass

        self.assertEqual(len(sleep_calls), 1)
        self.assertEqual(sleep_calls[0], 1)  # initial backoff is 1s


if __name__ == '__main__':
    unittest.main()
