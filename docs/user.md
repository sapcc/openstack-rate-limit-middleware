User documentation
------------------

The OpenStack rate limit middleware allows controlling the number of incoming requests on global and project level for an OpenStack API. 
Find more details in the [documentation](strategies.md).

The response will indicate if the user was rate limited provide additional information via headers as shown below. 

| Header                  | Description |
|-------------------------|-------------|
| X-RateLimit-Limit       | The limit for the current request in the format `<n>r/<m><t>`. <br> Read: Limit to `n` requests per window `m` <unit>. Valid interval units are `s, m, h, d`. |
| X-RateLimit-Remaining   | The number of remaining requests within the current window. |
| X-RateLimit-Retry-After | How long a client should wait  |
| X-Retry-After           | For compatibility with OpenStack Swift. Same as `X-RateLimit-Retry-After`. |

 
Example when *not* being rate limited:
```bash
curl -i https://$openstackAPI
HTTP/1.1 200 OK
Status: 200 OK
X-RateLimit-Limit: 60r/m
X-RateLimit-Remaining: 59
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
| openstack_ratelimit_requests_global_ratelimit_total | Amount of rate limited requests due to the global rate limit. |
| openstack_ratelimit_requests_local_ratelimit_total  | Amount of rate limited requests due to the local (per scope) rate limit. |

All metrics come with the following labels:

| Label name      | Description |
|-----------------|-------------|
| service         | The service type according to CADF specification. |
| service_name    | The name of the OpenStack service. |
| action          | The CADF action of the request. |
| scope           | The scope of the request. |
| target_type_uri | The CADF target type URI of the request. |
