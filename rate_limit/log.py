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

from oslo_config import cfg
from oslo_log import log as logging

CONF = cfg.CONF


class Logger(object):
    """
    Logger that attempts to log and ignores any error.

    """
    def __init__(self, name, product_name='rate_limit'):
        self.__logger = logging.getLogger(name)
        try:
            logging.register_options(CONF)
            logging.setup(CONF, product_name)
        except cfg.ArgsAlreadyParsedError:
            # Ignore error if args are already registered.
            pass

    def info(self, msg):
        try:
            self.__logger.info(msg)
        except Exception:
            pass

    def warning(self, msg):
        try:
            self.__logger.warning(msg)
        except Exception:
            pass

    def warning(self, msg):
        try:
            self.__logger.error(msg)
        except Exception:
            pass

    def debug(self, msg):
        try:
            if CONF.debug or os.getenv("DEBUG", False):
                self.__logger.debug(msg)
        except Exception:
            pass
