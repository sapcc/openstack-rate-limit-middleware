Installation
------------

Install this middleware via
```
pip install git+https://github.com/sapcc/openstack-rate-limit-middleware.git 
```

### Pipeline 

This middleware relies on the request classification provided by the [openstack-watcher-middleware](https://github.com/sapcc/openstack-watcher-middleware)
and must be added after it:
```
pipeline = .. sapcc-watcher sapcc-rate-limit ..
```

## WSGI configuration

The following parameters are provided via the WSGI configuration:
```yaml
# The service type according to CADF specification.
service_type:                   <string>

# Path to the configuration file.
config_file:                    <string>

# If this middleware enforces rate limits in multiple replicas of an API,
# the clock accuracy of the individual replicas can be configured as follows.
clock_accuracy:                 <n><unit> (default: 1ms)

# Per default rate limits are applied based on `initiator_project_id`.
# However, this can also be se to `initiator_host_address` or `target_project_id`.
rate_limit_by:                  <string>

# The maximal time a request can be suspended in seconds.
# Instead of immediately returning a rate limit response, a request can be suspended
# until the specified maximum duration to fit the configured rate limit. 
# This feature can be disabled by setting the max sleep time to 0 seconds.
max_sleep_time_seconds:         <int> (default: 20)

# Log requests that are going to be suspended for log_sleep_time_seconds <= t <= max_sleep_time_seconds.
log_sleep_time_seconds:         <int> (default: 10)

# Emit Prometheus metrics via StatsD.
# Host of the StatsD exporter.
statsd_host:                    <string> (default: 127.0.0.1)

# Port of the StatsD exporter.
statsd_port:                    <int> (default: 9125)

# Prefix to apply to all metrics provided by this middleware.
statsd_prefix:                  <string> (default: openstack_ratelimit_middleware)

# Host for redis backend.
backend_host:                   <string> (default: 127.0.0.1)

# Port for redis backend.
backend_port:                   <int> (default: 6379)

# Maximum connections for redis connection pool.
backend_max_connections:        <int> (default: 100)

# Timeout for obtaining a connection to the backend.
# Skips rate limit on timeout.
backend_timeout_seconds:        <int> (default: 20)

## Configure Limes as provider for rate limits.
# See the limes guide for more details.
limes_enabled:                  <bool> (default: false)

# URI of the Limes API.
# If not provided, the middleware attempts to autodiscover the URI of the Limes API using the  
# service catalog of the Keystone token.
limes_api_uri:                  <string>

# To avoid querying for rate limits for each requests, rate limits obtained from Limes are cached in Redis.
# Specify the interval in which cached rate limits are refreshed in seconds.
# Setting 0 here disabled the caching. The middleware will query Limes for rate limits for every requests.
# This might have a negative effect on your applications performance.
limes_refresh_interval_seconds: <int> (default: 300)

# Credentials of the OpenStack service user able to read rate limits from Limes.
identity_auth_url:              <string>
username:                       <string>
user_domain_name:               <string>
password:                       <string>
domain_name:                    <string>
```
