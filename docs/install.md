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
service_type:     <string>

# Path to the configuration file.
config_file:      <string>

# If this middleware enforces rate limits in multiple replicas of an API,
# the clock accuracy of the individual replicas can be configured as follows.
clock_accuracy:   <n><unit> (default 1ms)

# Per default rate limits are applied based on `initiator_project_id`.
# However, this can also be se to `initiator_host_address` or `target_project_id`.
rate_limit_by:    <string>

# The maximal time a request can be suspended in seconds.
# Instead of immediately returning a rate limit response, a request can be suspended
# until the specified maximum duration to fit the configured rate limit. 
max_sleep_time_seconds: <int> (default: 20)

# Log requests that are going to be suspended for log_sleep_time_seconds <= t <= max_sleep_time_seconds.
log_sleep_time_seconds: <int> (default: 10)

# Emit Prometheus metrics via StatsD.
# Host of the StatsD exporter.
statsd_host:      <string> (default: 127.0.0.1)

# Port of the StatsD exporter.
statsd_port:      <int> (default: 9125)

# Prefix to apply to all metrics provided by this middleware.
statsd_prefix:    <string> (default: openstack_ratelimit_middleware)

# The backend used to store number of requests.
# Choose between redis, memcache.
backend:          <string> (default: redis)

# Host for backend.
backend_host:     <string> (default: 127.0.0.1)

# Port for backend.
backend_port:     <int> (default: 6379)

## Limes configuration.
# Rate limits con be provided via Limes.
limes_enabled:    <bool> (default: false)
# Credentials of the OpenStack service user able to read rate limits from Limes.
auth_url:         <string>
username:         <string>
user_domain_name: <string>
password:         <string>
domain_name:      <string>
```
