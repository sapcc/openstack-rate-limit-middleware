OpenStack Rate Limit Middleware
===============================

The OpenStack Rate Limit Middleware enables traffic control for OpenStack APIs per *target type uri*, *action*, *scope* (project, host address).

Prerequisites
-------------

A scheme of classification for OpenStack request is required which maps an API call to an *action*, a path' to *target_type_uri*  and 
extracts a scope from the token.
This is done by the [openstack-watcher-middleware](https://github.com/sapcc/openstack-watcher-middleware), 
which watches and classifies requests based on the [DMTF CADF specification](https://www.dmtf.org/standards/cadf).

Usage and Configuration
-----------------------

## Configure rate limits

Rate limits can be configured via a configuration file and/or via [Limes](https://github.com/sapcc/limes).  
Limits defined in a configuration file are applied per project, but they might be overwritten by project-specific limits
configured in Limes.
The syntax for minimal configuration of rate limits is described below.
```
rates:
    <target_type_uri>:
        - action:   <action type>
          # limit to n requests per m <unit> 
          # valid interval units are `s, m, h, d`.
          limit:    <n>r/<m><t>
          strategy: <rate limit strategy>
```

Example for Swift (object-store):
```
rates:
  account/container:
    - action: update
      limit: 5r/s
      strategy: fixedwindow
    - action: create
      limit: 2r/5m
      strategy: slidingwindow
``` 

## Rate Limit Strategy

This middleware offers rate limit strategies for multiple scenarios as described hereinafter.

### (1) Fixed window strategy

**TLDR**: This strategy is recommended for enforcing a rate limit with a **high ratio of requests per interval**. 

Configuring a rate limit of a number of `n requests` per `t interval` means that a request is allowed every `ts = t/n`.
If the maximum of requests per time window was reached new requests are either queued or rejected with a *RateLimitExceededResponse*.
Each incoming requests in the same scope will increase the queue time until a configurable maximum (`max_sleep_time_seconds`),
 after which an immediate *RateLimitExceededResponse* is sent.
 
Syntax for enforcing a rate limit using the fixed window strategy:
```
limit: <n>r/<unit>

<n>...      number of requests within the interval
<unit>...   unit such as s, m
```

Example configuration:
```
rates:
  account/container:
    - action: update
      limit: 5r/s
    - action: create
      limit: 2r/s
``` 

API configuration for fixed window strategy:
```
# rate limit response is returned if sleep time exceeds this value
max_sleep_time_seconds: <int> (default: 20)

# number of seconds the rate counter can drop
# larger number results in larger spikes but better average
rate_buffer_seconds: <int> (default: 5)
```

**Notes/Limitations**:  
Especially for enforcing rate limits with a very low ratio of requests/interval configuring a reasonable `max_sleep_time_seconds`
 is important to avoid client side timeouts due to a too long queuing in the middleware. 
Example: Configuring rate limit of `1r/m` and `max_sleep_time_seconds=60` would mean the 2nd request could be queued for up to 60s
 (assuming the first request is handled at 0s).
 
Relevant for rate limits in the range of *minutes or more*: 
The number of actual requests can exceed the configured interval by a factor of 2, if requests are coming at the end of a time window and 
    right at the beginning of the next window.
 
### (2) Sliding window strategy

**TLDR**: This strategy is recommended for enforcing rate limits in the range of **requests/minute - day**.

Requests are rate-limited within a configurable interval - a sliding window.
The sliding window is calculated for each incoming request by looking at the past requests within the configured time.
This strategy enables more complex scenarios, for example `2r/m`, `1000r/h`, `100r/15m`, etc. . 

Syntax for enforcing a rate limit using the sliding window strategy: `<n>r/<m><unit>`.
```
limit: <n>r/<m><unit>

<n>...      number of requests within the interval
<m>...      interval factor
<unit>...   unit such as s, m, h, d
```

Example configuration:
```
rates:
  account/container:
    - action: update
      limit: 5r/15m
      strategy: slidingwindow
    - action: read
      limit: 100r/m
      strategy: slidingwindow
``` 

## Optional global settings

The following section describes optional global settings and their defaults.  

Provided via API configuration:
```
# if this middleware enforces rate limits in multiple replicas of an API,
# the clock accuracy of the individual replicas can be configured as follows
clock_accuracy: <n><unit> (default 1ms)

# per default rate limits are applied based on `initiator_project_id`
# however, this can also be se to `initiator_host_address` or `target_project_id`
rate_limit_by: <rate_limit_by>

```

Provided via configuration file:  
```
# customize rate limit response
rate_limit_response:
  # sett additional headers
  headers:
    Foo: Bar
  # http response status
  status: 498 Rate Limited
  # specify either body or json_body
  # body: 'Rate Limit Exceeded'
  json_body: '{ "message": "important" }'

# custom blacklist response
blacklist_response:
  # http response status
  status: 497 Blacklisted
  headers:
    X-Foo: Bar
  # specify content_type
  content_type: "application/json"
  # specify either body or json_body
  json_body: {"error": {"status": "497 Blacklisted", "message": "You have been blacklisted. Please contact and administrator."}}

# list of blacklisted projects by uid
blacklist:
    - <project_id>
    - <project_id>

# list of whitlisted projects by uid
whitelist:
    - <project_id>
    - <project_id>

rates:
    ...
```
