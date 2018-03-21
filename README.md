OpenStack Rate Limit Middleware
===============================

The OpenStack Rate Limit Middleware enables traffic control for OpenStack APIs per given scope, resource and action.

Prerequisites
-------------

This middleware does not provide a mechanism to analyze requests and map to actions.  
However, this is done by [a common, dedicated middleware](insert link here), which parses the requests and provides 
  a unified taxonomy for scope, resource, action keys.
  

Usage and Configuration
-----------------------

## Rate Limit Strategy

This middleware offers the following rate limit strategies.
How to choose the best strategy is described in this part. 
How to configure them can be seen in the example configuration snippet further below.  
Valid interval units are `s, m, h, d`.

### (1) Fixed window strategy

TLDR; This strategy is recommended for enforcing a rate limit with a **high ratio of requests per interval**. 

Configuring a rate limit of a number of `n requests` per `t interval` means that a request is allowed every `ts = t/n`.
If the maximum of requests per time window was reached new requests are either queued or rejected with a *RateLimitExceededResponse*.
Each incoming requests in the same scope will increase the queue time until a configurable maximum (`max_sleep_time_seconds`),
 after which an immediate *RateLimitExceededResponse* is sent.
 
Syntax for enforcing a rate limit of `<number> of r requests` per `<unit> interval`: `<number>r/<unit>`. 

Example configuration:
```
rate_limits:
- resource: 'compute/server'
  actions:
  - action: create
    limit: 5r/s
    strategy: FixedWindow
    max_sleep_time_seconds: 10
    rate_buffer_seconds: 5
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

TLDR; This strategy is recommended for enforcing rate limits in the **requests/minute - day**.

Requests consume tokens. Tokens replenish after a configurable time (window) has passed. 
The sliding window is calculated for each incoming request by looking at the past requests within the configured time.
This strategy enables more rate limit scenarios, ranging from `2r/m`, `1000r/h` to `100r/15m`.  

Syntax for enforcing a rate limit of `<number> of r requests` per `<window> sliding window` `<unit> interval`: `<number>r/<window><unit>`. 

Example configuration:
```
rate_limits:
- resource: 'compute/server'
  actions:
  - action: create
    limit: 5r/30m
    strategy: SlidingWindow
``` 

## Optional global settings

The following section describes optional global settings and their defaults:
```
# If this middleware enforces rate limits in multiple replicas of an API,
#   the clock accuracy of the individual replicas can be configured as follows
clock_accuracy: 1ms

# customize rate limit response
rate_limit_response:
  headers:
    Foo: Bar
  # any valid http status code
  code: 200
  # specify either body or json_body
  # body: '<html> <head> <title>Rate Limit Exceeded</title> </head> <body> <h1>Rate Limit Exceeded</h1> </body> </html>'
  json_body: '{ "message": "important" }'
```
