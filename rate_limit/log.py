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

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)-15s %(levelname)s %(message)s')


class Logger(object):
    """
    Logger that attempts to log and ignores any error.

    """
    def __init__(self, name):
        self.__logger = logging.getLogger(name)

    def setLevel(self, level=logging.INFO):
        self.__logger.setLevel(level)

    def info(self, msg):
        try:
            self.__logger.info(msg)
        except Exception:
            pass

    def warning(self, msg):
        print msg
        try:
            self.__logger.warning(msg)
        except Exception:
            pass

    def debug(self, msg):
        try:
            self.__logger.debug(msg)
        except Exception:
            pass
