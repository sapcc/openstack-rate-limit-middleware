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
from webob import Response


class FakeMemcached(object):
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key, None)

    def set(self, key, value):
        self.store[key] = value
        return True

    def incr(self, key, delta=1, time=0):
        value = int(self.store.setdefault(key, 0)) + int(delta)
        if value < 0:
            value = 0
        self.store[key] = value
        return int(value)

    def decr(self, key, delta=1, time=0):
        return self.incr(key, delta=-delta, time=time)

    def delete(self,key):
        try:
            del self.store[key]
        except KeyError:
            pass
        return True


class FakeApp(object):
    def __call__(self, environ, start_response):
        return Response(json_body='{"message":"fake app"}')(environ, start_response)


class FakeKeystoneclient(object):
    def __init__(self):
        self.session = FakeSession()


class FakeSession(object):
    def get_token(self):
        return "OS_TOKEN"
