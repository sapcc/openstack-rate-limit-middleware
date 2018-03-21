OpenStack Rate Limit Middleware
===============================

The OpenStack Rate Limit Middleware enables traffic control for OpenStack APIs per *target type uri*, *action*, *scope* (project, host address).

Prerequisites
-------------

A scheme of classification for OpenStack request is required which maps an API call to an *action*, a path' to *target_type_uri*  and 
extracts a scope from the token.
This is done by the [openstack-watcher-middleware](https://github.com/sapcc/openstack-watcher-middleware), 
which watches and classifies requests based on the [DMTF CADF specification](https://www.dmtf.org/standards/cadf).

## Installation & Usage

Install via
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
  global:
    account/container:
      # limit container updates to 5 requests per second
      - action: update  
        limit: 5r/s
      # limit container creations to 2 requests every 5 minutes
      - action: create 
        limit: 2r/5m
``` 

### Global, local and default rate limits

This middleware 
Read more on how to configure global, local and default rate limits in the [configuration section](./docs/configuration.md).


### Rate Limit Strategies

This middleware offers rate limit strategies for multiple scenarios. Read more [here](./docs/strategies.md#strategies).
