Configuration
=============

This sections provides an overview of the configurable options via WSGI config and configuration file.

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

## WSGI configuration

The following parameters are provided via the WSGI configuration:
```yaml
# if this middleware enforces rate limits in multiple replicas of an API,
# the clock accuracy of the individual replicas can be configured as follows
clock_accuracy: <n><unit> (default 1ms)

# per default rate limits are applied based on `initiator_project_id`
# however, this can also be se to `initiator_host_address` or `target_project_id`
rate_limit_by: <rate_limit_by>
```

## Configuration file

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
    <target_type_uri>:
        - action:   <action type>
          # limit to n requests per m <unit> 
          # valid interval units are `s, m, h, d`.
          limit:    <n>r/<m><t>
          strategy: <rate limit strategy>
```

