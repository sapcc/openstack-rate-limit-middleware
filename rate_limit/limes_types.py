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

import json

from . import common


class LimesProjectList(object):
    """
    Wrapper class for the listing rate limits from Limes.
    """
    def __init__(self, projects, *args, **kwargs):
        self.projects = []
        for p in projects:
            self.projects.append(
                LimesProject(
                    id=p.get('id', None),
                    services=p.get('services', [])
                )
            )

    def get_rate_limit(self, project_id, service_type, target_type_uri, action):
        """
        Get a rate limit for a set of service type, project ID, target type URI and action.

        :param project_id: the UUID of the project
        :param service_type: the service type of the rate limit
        :param target_type_uri: the target type URI of the rate limit
        :param action: the action of the rate limit
        :return: the rate limit or None
        """
        for p in self.projects:
            if p.id == project_id:
                return p.get_rate_limit(service_type, target_type_uri, action)

    def to_key_rate_limit_dict(self, service_type=None):
        """
        Get a dictionary { <key> : <rate_limit> }, where key = <project_id>_<target_type_uri>_<action>
        of all rate limits obtained from Limes.
        Allows filtering rate limits for a specfic service type.

        :param service_type: the service type
        :return: all rate limits as a dictionary or {}
        """
        d = {}
        for pr in self.projects:
            for svc in pr.services:
                if service_type and svc.type != service_type:
                    continue
                for rl in svc.rates:
                    for act in rl.actions:
                        key = common.key_func(
                            scope=pr.id,
                            target_type_uri=rl.target_type_uri,
                            action=act.name,
                            prefix='limes',
                        )
                        d[key] = act.limit
        return d


class LimesProject(object):
    def __init__(self, id, services, *args, **kwargs):
        self.id = id
        self.services = []
        for s in services:
            self.services.append(
                LimesService(
                    type=s.get('type', None),
                    area=s.get('area', None),
                    rates=s.get('rates', [])
                )
            )

    def get_rate_limit(self, service_type, target_type_uri, action_name):
        for s in self.services:
            if s.type == service_type:
                return s.get_rate_limit(target_type_uri, action_name)


class LimesService(object):
    def __init__(self, type, area, rates):
        self.type = type
        self.area = area
        self.rates = []
        for r in rates:
            self.rates.append(
                LimesProjectRateLimit(
                    target_type_uri=r.get('targetTypeURI', None),
                    actions=r.get('actions', [])
                )
            )

    def get_rate_limit(self, target_type_uri, action_name):
        for r in self.rates:
            if r.target_type_uri == target_type_uri:
                return r.get_rate_limit(action_name)


class LimesProjectRateLimit(object):
    def __init__(self, target_type_uri, actions):
        self.target_type_uri = target_type_uri
        self.actions = []
        for a in actions:
            self.actions.append(
                LimesRateLimitAction(
                    name=a.get('name', None),
                    limit=a.get('limit', None)
                )
            )

    def get_rate_limit(self, action_name):
        for a in self.actions:
            if a.name == action_name:
                return a.limit
        return None


class LimesRateLimitAction(object):
    def __init__(self, name, limit):
        self.name = name
        self.limit = limit


def decode_limes_json(json_raw):
    j = json.loads(json_raw)
    return LimesProjectList(**j)
