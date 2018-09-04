OpenStack Rate Limit Middleware
===============================

[![Build Status](https://travis-ci.org/sapcc/openstack-rate-limit-middleware.svg?branch=master)](https://travis-ci.org/sapcc/openstack-rate-limit-middleware)

The OpenStack Rate Limit Middleware enables traffic control for OpenStack APIs per *target type uri*, *action*, *scope* (project, host address).

Prerequisites
-------------

A scheme of classification for OpenStack requests is required which characterizes API requests.  
This is implemented by the [openstack-watcher-middleware](https://github.com/sapcc/openstack-watcher-middleware), 
which watches and classifies requests based on the [DMTF CADF specification](https://www.dmtf.org/standards/cadf).  
Eventually, in terms of rate limiting, a request to a service can be described by an *action*, *target type URI*.

## Installation & Usage

Install this middleware via
```
pip install git+https://github.com/sapcc/openstack-rate-limit-middleware.git 
```

### Pipeline 

The rate limit middleware should be added after the [openstack-watcher-middleware](https://github.com/sapcc/openstack-watcher-middleware):
```
pipeline = .. sapcc-watcher sapcc-rate-limit ..
```

## Configuration

Rate limits can be configured via a configuration file and/or via [Limes](https://github.com/sapcc/limes).  
The following snippet illustrates how global rate limits for each project are defined via the configuration file.  
More information is provided in the [configuration section](./docs/configuration.md).

Example for Swift (object-store):
```yaml
rates:
  # global rate limits. counted across all projects
  global:
    account/container:
      # limit container updates to 100 requests per second
      - action: update  
        limit: 100r/s
      # limit container creations to 100 requests per second
      - action: create 
        limit: 100r/s
  
  # default local rate limits. counted per project
  default:
    account/container:
      # limit container updates to 10 requests per minute
      - action: update  
        limit: 10r/m
      # limit container creations to 5 requests every 10 minutes
      - action: create 
        limit: 5r/10m
``` 

### Global, local and default rate limits

This middleware can be used to enforce rate limits on multiple levels. 
Read more on how to configure global, local and default rate limits in the [configuration section](./docs/configuration.md).


### Rate Limit Strategies

This middleware offers rate limit strategies for multiple scenarios. Read more [here](./docs/strategies.md#strategies).
