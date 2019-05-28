Configuration
=============

This sections provides an overview of the configurable options via WSGI config and configuration file.

## Global and local rate limits

Rate limits can be enforced on 2 levels: Global and local.
  
- Global rate limits  
  Every request passing this middleware, regardless of their scope (project, domain, host address) is counted.
  If the number of requests per action and target type URI within the configured window would exceed the configured maximum,
    a configurable rate limit response is sent until the number of requests within the window is again below the maximum.

- Local rate limits  
  Requests are counted per local scope (project, domain or initiator host address).
  If the number of requests per scope, action, target type URI within the specified window would exceed the configured maximum,
    a configurable rate limit response is sent until the number of requests within the window is again below the maximum.

## Configure rate limits

Rate limits can be configured via a *configuration file* and/or via [*Limes*](https://github.com/sapcc/limes). 
The configuration file can only be used to specify global rate limits and defaults for local rate limits.
If scope (project, domain) specific rate limits are required, they have to be set via Limes. 
See the [examples](../etc/) for more details.    

The syntax for minimal configuration of rate limits is described below.
```yaml
rates:
    <level>:
        <target_type_uri>:
            - action:   <action type>
              # limit to n requests per m <unit> 
              # valid interval units are `s, m, h, d`.
              limit:    <n>r/<m><t>
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

## Black- & Whitelist

This middleware allows black- and whitelist certain scopes via configuration file.
Also see the [examples](../etc/).  

```yaml
# List of blacklisted projects by uid.
blacklist:
    - <project_id>
    - <project_id>

# List of whitelisted projects by uid.
whitelist:
    - <project_id>
    - <project_id>
```

Furthermore, the blacklist and rate limit responses can be configured as shown below.   
```yaml
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
```
