OpenStack Rate Limit Middleware
===============================

[![Build Status](https://travis-ci.org/sapcc/openstack-rate-limit-middleware.svg?branch=master)](https://travis-ci.org/sapcc/openstack-rate-limit-middleware) [![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)


The OpenStack Rate Limit Middleware enforces rate limits and enables traffic shaping for OpenStack APIs per tuple of
- *target type URI*
- *action*
- *scope* (project, host address)

It also supports enforcing global and scoped rate limits.
More details can be found in the documentation.

## Prerequisites

This middleware requires the classification for OpenStack requests.  
The [openstack-watcher-middleware](https://github.com/sapcc/openstack-watcher-middleware) can be used to classify requests
based on the [DMTF CADF specification](https://www.dmtf.org/standards/cadf).
In terms of rate limiting, a request to an OpenStack service can be described by an *action*, *target type URI* and its *scope*.

Moreover, this middleware uses `Redis >= 5.0.0` as a backend to store rate limits.

## Documentation

- [Installation & WSGI configuration](./docs/install.md)
- [How to configure rate limits](./docs/configure.md)
- [User guide](./docs/user.md)
