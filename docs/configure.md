Middleware configuration
------------------------

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


## Black- & Whitelist

This middleware allows configuring a black- and whitelist for certain scopes as show below.
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

## Example configuration

Rate limits can be configured via a configuration file and/or via [Limes](https://github.com/sapcc/limes).  
The following snippet illustrates how global rate limits for each project are defined via the configuration file.  
More information is provided in the [configuration section](./docs/configuration.md).

Example for Swift (object-store):
```yaml
rates:
  # global rate limits. counted across all projects
  global:
    account/container:
      # limit container updates to 100 requests per second
      - action: update  
        limit: 100r/s
      # limit container creations to 100 requests per second
      - action: create 
        limit: 100r/s
  
  # default local rate limits. counted per project
  default:
    account/container:
      # limit container updates to 10 requests per minute
      - action: update  
        limit: 10r/m
      # limit container creations to 5 requests every 10 minutes
      - action: create 
        limit: 5r/10m
``` 
