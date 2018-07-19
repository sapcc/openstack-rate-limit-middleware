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

import requests

from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client


class Limes(object):
    def __init__(self):
        self.limes_base_url = self._get_limes_base_url_from_catalog()

    def _authenticate(self, auth_url, user_id, password, domain_id):
        auth = v3.Password(
            auth_url=auth_url,
            user_id=user_id,
            password=password,
            domain_id=domain_id
        )
        sess = session.Session(auth=auth)
        return client.Client(session=sess)

    def _get_limes_base_url_from_catalog(self):
        if not self.keystone.has_service_catalog():
            return None

        for service in self.keystone.service_catalog:
            print service

        #TODO
        return ''

    def list_ratelimits_for_projects_in_domain(self, domain_id, project_id=None, service=None):
        """
        Query limes for rate limits for projects in a domain
        :param domain_id: the domain uid
        :param project_id: optional project uid
        :param service: limit query to a service
        :return: dictionary of projects and their rates in the given domain
        """
        if not domain_id:
            return

        path = '/v1/domains/{0}/projects'.format(domain_id)
        if project_id:
            path += '/projects/{0}'.format(project_id)

        params = {}
        if service:
            params['service'] = service

        return self._get(path, params)

    def _get(self, path, params={}, headers={}):
        if not params:
            params = {}
        if not headers:
            headers = {}

        # only list rates
        params['rates'] = True

        # set X-AUTH-TOKEN header
        headers['X-AUTH-TOKEN'] = self.keystone.get_token()
        url = self.limes_base_url + path

        resp = requests.get(url=url, params=params, headers=headers)
        return resp.json()
