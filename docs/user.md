User documentation
------------------

The OpenStack rate limit middleware allows controlling the number of incoming requests on a global and project level as well as per host IP for an OpenStack API.
Additionally, this middleware supports slowing down requests instead of immediately returning a rate limit response.
A request can be suspended for configurable duration in order to fit the rate limit.

The response will indicate if the user was rate limited provide additional information via headers as shown below. 

| Header                  | Description |
|-------------------------|-------------|
| X-RateLimit-Limit       | The limit for the current request in the format `<n>r/<m><t>`. <br> Read: Limit to `n` requests per window `m` <unit>. Valid interval units are `s, m, h, d`. |
| X-RateLimit-Remaining   | The amount of remaining requests within the current window. |
| X-RateLimit-Retry-After | How long a client should wait before attempting to make another request.  |
| X-Retry-After           | For compatibility with OpenStack Swift. Same as `X-RateLimit-Retry-After`. |

 
Example when *not* being rate limited:
```bash
curl -i https://$openstackAPI
HTTP/1.1 200 OK
Status: 200 OK
```

Example when sending too many requests in a given amount of time (sliding window):
```bash
curl -i https://$openstackAPI
HTTP/1.1 429 Too Many Requests
Status: 429 Too Many Requests
X-RateLimit-Limit: 60r/m
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 60
X-Retry-After: 60
```

# Metrics

This middleware emits the following [Prometheus metrics](https://prometheus.io/docs/concepts/metric_types) via [StatsD](https://github.com/DataDog/datadogpy).  

| Metric name                                         | Description |
|-----------------------------------------------------|-------------|
| openstack_ratelimit_requests_whitelisted_total      | Amount of whitelisted requests. |
| openstack_ratelimit_requests_blacklisted_total      | Amount of blacklisted requests. |
| openstack_ratelimit_requests_ratelimit_total        | Amount of rate limited requests due to a global or local rate limit. |

All metrics come with the following labels:

| Label name      | Description |
|-----------------|-------------|
| service         | The service type according to CADF specification. |
| service_name    | The name of the OpenStack service. |
| action          | The CADF action of the request. |
| scope           | The scope of the request. |
| target_type_uri | The CADF target type URI of the request. |

In addition the `openstack_ratelimit_requests_ratelimit_total` metric comes with a `level` label indicating whether a global or local rate limit was the limit. 

# Burst requests

This middleware is capable of handling a burst of requests as described hereinafter.

## With delay

This middleware handles requests that would exceed the configured rate by delaying them until the next possible slot but not longer than `max_sleep_time_seconds`.
See the [WSGI section](install.md) on how to configure this. 

Example:  
Given a `rate limit=1r/m` and a `max_sleep_time_seconds=20`, the 1st request at t<sub>1</sub>=0 would be processed just fine. 
However, a 2nd request received within the one minute window after the 1st request would exceed the rate limit.
Assuming it's received at t<sub>2</sub>=45, the request would not be rejected but suspended for 15 seconds and processed afterwards so that the rate of `1r/m` is not exceeded. 

However, this behaviour might let your application appear slow for a user since request can be suspended for as long as `max_sleep_time_seconds`.
It can be disabled by setting `max_sleep_time_seconds=0`.
In which case every requests that exceeds the defined rate limits immediately gets rejected.
