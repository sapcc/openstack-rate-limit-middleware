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
See the [examples](../etc/) for more details.  
If scope (project, domain) specific rate limits are required, they have to be set via Limes.  

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
# the service type according to CADF specification
service_type:     <type>

# path to the configuration file
config_file:      <path>

# if this middleware enforces rate limits in multiple replicas of an API,
# the clock accuracy of the individual replicas can be configured as follows
clock_accuracy:   <n><unit> (default 1ms)

# per default rate limits are applied based on `initiator_project_id`
# however, this can also be se to `initiator_host_address` or `target_project_id`
rate_limit_by:    <rate_limit_by>

# Emit Prometheus metrics via StatsD
# address of the StatsD exporter
statsd_host:      <host> (default: 127.0.0.1)

# port of the StatsD exporter
statsd_port:      <port> (default: 9125)

# prefix to apply to all metrics provided by this middleware
statsd_prefix:    <prefix> (default: openstack_ratelimit_middleware)

# MemCache is used to store count of requests and cache rate limits from limes
memcache_host:    <host> (default: 127.0.0.1)

# Rate limits can be configured in Limes
limes_enabled:    <enabled bool> (default: false)
# Credentials of the OpenStack service user able to read rate limits from Limes
auth_url:         <keystone auth endpoint >
username:         <service username>
user_domain_name: <domain of the service user>
password:         <password of the service user>
domain_name:      <domain name>
```

## Configuration file

Examples are provided [here](../etc/).
The following parameters are provided via the configuration file:
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

# list of blacklisted projects by uid
blacklist:
    - <project_id>
    - <project_id>

# list of whitlisted projects by uid
whitelist:
    - <project_id>
    - <project_id>

rates:
    <level>:
        <target_type_uri>:
            - action:   <action type>
              # limit to n requests per m <unit> 
              # valid interval units are `s, m, h, d`.
              limit:    <n>r/<m><t>
```
