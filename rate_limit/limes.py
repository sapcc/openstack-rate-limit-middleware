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

from oslo_log import log
from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client


class Limes(object):
    def __init__(self, logger=log.getLogger(__name__)):
        self.logger = logger
        self.keystone = None
        self.limes_base_url = None

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
        if not self.limes_base_url:
            self._get_limes_base_url()

        # only list rates
        params['rates'] = True

        # set X-AUTH-TOKEN header
        headers['X-AUTH-TOKEN'] = self.keystone.session.get_token()
        url = self.limes_base_url + path

        resp = requests.get(url=url, params=params, headers=headers)
        return resp
