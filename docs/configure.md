Middleware configuration
------------------------

This sections provides an overview of the configurable options via WSGI config and configuration file.

# Global and local rate limits

Rate limits can be enforced on 2 levels: Global and local.
  
- Global rate limits  
  Every request passing this middleware, regardless of their scope (project, domain, host address) is counted.
  If the number of requests per action and target type URI within the configured window would exceed the configured maximum,
    a configurable rate limit response is sent until the number of requests within the window is again below the maximum.

- Local rate limits  
  Requests are counted per local scope (project, domain or initiator host address).
  If the number of requests per scope, action, target type URI within the specified window would exceed the configured maximum,
    a configurable rate limit response is sent until the number of requests within the window is again below the maximum.

# Configure rate limits

Rate limits can be configured via a *configuration file* and/or via [*Limes*](https://github.com/sapcc/limes). 
The configuration file can only be used to specify global rate limits and defaults for local rate limits.
If scope (project, domain) specific rate limits are required, they have to be set via Limes. 
See the [examples](../etc/) for more details.    

The syntax for minimal configuration of rate limits is described below.
```yaml
rates:
    <level>:
        <target_type_uri>:
              # The name of the action.
            - action:   <action type>
            
              # Limit to n requests per m <unit>. 
              # Valid interval units are `s, m, h, d`.
              limit:    <n>r/<m><t>
```

## Rate limit groups

A set of CADF actions can be logically grouped and - in terms of rate limiting - be count

Example:  
The CADF actions `udpate`, `delete` are part of the `write` rate limit group.
Thus any `update` or `delete` request will be jointly assessed as a `write` request. The middleware considers only the rate limit for `write`.  

```yaml
groups:
  write:
    - update
    - delete

  read:
    - read
    - read/list

rates:
  global:
    account/container:
      - action: write
        limit: 1r/m
      - action: create
        limit: 2/rm

  default:
    account/container:
      - action: write
        limit: 2r/m

    account/container/object:
      - action: read
        limit: 3r/m
```

## Example configuration

Rate limits can be specified via a configuration file and/or via [Limes](https://github.com/sapcc/limes).  
The following snippet illustrates how global rate limits per backend and defaults for each project are defined via the configuration file.  
More information is provided in the [configuration section](./docs/configuration.md).

Example for Swift (object-store):
```yaml
rates:
  # Global rate limits. Counted across all projects.
  global:
    account/container:
      # limit container updates to 100 requests per second
      - action: update  
        limit: 100r/s

      # limit container creations to 100 requests per second
      - action: create 
        limit: 100r/s
  
  # Default local rate limits. Counted per project.
  default:
    account/container:
      # limit container updates to 10 requests per minute
      - action: update  
        limit: 10r/m
        
      # limit container creations to 5 requests every 10 minutes
      - action: create 
        limit: 5r/10m
``` 

## Black- & Whitelist

This middleware allows configuring a black- and whitelist for certain scopes.
A scope might be an (initiator/target) project UUID or an initiator host address.   
If a scope is blacklisted, the middleware immediately returns the configured blacklist response. 
Requests in a whitelisted scope are not rate limited.  
Also see the [examples](../etc/).  

```yaml
# List of blacklisted scopes (project UUID, host address).
blacklist:
    - <scope>

# List of whitelisted scoped (project UUID, host address).
whitelist:
    - <scope>
```

## Customize responses

The blacklist and rate limit responses can be configured as shown below.  
A custom response requires the **status**, **status_code** and **body** or **json_body** to be specified.
```yaml
rate_limit_response:
  # HTTP response status string.
  status: 498 Rate Limited
  
  # HTTP response status code.
  status_code: 498
  
  # Specify *either* body or json_body.
  body:  "<html><body><h1>Rate limit exceeded</h1></body></html>"
  # json_body: { "message": "rate limit exceeded" }
  
  # Optional: Set additional headers.
  headers:
    X-SERVICE: SOMETHING

blacklist_response:
  # HTTP response status string.
  status: 497 Blacklisted
  
  # HTTP response status code.
  status_code: 497
  
  # Specify *either* body or json_body.
  body:  "<html><body><h1>You have been blacklisted. Contact an administrator.</h1></body></html>"
  # json_body: { "message": "You have been blacklisted. Please contact and administrator." }
  
  # Optional: Set additional headers.
  headers:
    X-SERVICE: SOMETHING
```

# Testing

This middleware offers a variety of options for rate limiting and traffic shaping for an OpenStack API.  
Whether the current configuration and behaviour matches the users expectations can be verified using [siege](https://github.com/JoeDog/siege) - a load testing and benchmarking toolkit.
Install on OSX using [homebrew](https://formulae.brew.sh/formula/siege) `brew install siege`.

Assuming that a valid token was issued by OpenStack Keystone and is available as `OS_AUTH_TOKEN`:
```bash
# Obtain token.
export OS_AUTH_TOKEN=$(openstack token issue -c id -f value)

# Send 10 concurrent requests to an endpoint and benchmark.
siege --concurrent=1 --reps=10 --benchmark -header="X-AUTH-TOKEN:$OS_AUTH_TOKEN" https://$OpenStackURI
```

Example: 

Test OpenStack Swift `POST account/container`

(1) Send 3 concurrent POST requests to update a Swift container using `siege`:
```bash
siege --concurrent=1 --reps=3 --benchmark --header="X-AUTH-TOKEN:$OS_AUTH_TOKEN" 'https://$OpenStackURI/v1/AUTH_$ProjectID/mycontainer POST'
```

The output for a rate of `1r/m` and `max_delay_seconds=0` (nodelay) could look as follows:
```bash
The server is now under siege...
HTTP/1.1 204     0.20 secs:       0 bytes ==> POST https://$OpenStackURI/v1/AUTH_$ProjectID/mycontainer
HTTP/1.1 498     0.09 secs:      19 bytes ==> POST https://$OpenStackURI/v1/AUTH_$ProjectID/mycontainer
HTTP/1.1 498     0.11 secs:      19 bytes ==> POST https://$OpenStackURI/v1/AUTH_$ProjectID/mycontainer
```
Only the 1st request is processed and the 2 subsequent, almost concurrently issued, requests are rejected as the rate limit of `1r/m` is exceeded.

(2) Send 10 requests with a a random delay of 1s to 10s between each request:
```bash
siege --reps=10 --delay=10 --header="X-AUTH-TOKEN:$OS_AUTH_TOKEN" 'https://$OpenStackURI/v1/AUTH_$ProjectID/mycontainer POST'
```

The output for a rate of `2r/m` and `max_delay_seconds=20` could look as follows:
```bash
The server is now under siege...
HTTP/1.1 204     0.36 secs:       0 bytes ==> POST https://$OpenStackURI/v1/AUTH_$ProjectID/mycontainer
HTTP/1.1 204     0.22 secs:       0 bytes ==> POST https://$OpenStackURI/v1/AUTH_$ProjectID/mycontainer
HTTP/1.1 498     0.10 secs:      19 bytes ==> POST https://$OpenStackURI/v1/AUTH_$ProjectID/mycontainer
HTTP/1.1 498     0.11 secs:      19 bytes ==> POST https://$OpenStackURI/v1/AUTH_$ProjectID/mycontainer
HTTP/1.1 498     0.12 secs:      19 bytes ==> POST https://$OpenStackURI/v1/AUTH_$ProjectID/mycontainer
HTTP/1.1 498     0.10 secs:      19 bytes ==> POST https://$OpenStackURI/v1/AUTH_$ProjectID/mycontainer
HTTP/1.1 204    19.72 secs:       0 bytes ==> POST https://$OpenStackURI/v1/AUTH_$ProjectID/mycontainer
HTTP/1.1 204     0.11 secs:       0 bytes ==> POST https://$OpenStackURI/v1/AUTH_$ProjectID/mycontainer
...
```

The 1st and 2nd request are successfully processed within the rate limit of `2r/m`. 
The 3rd to 6th requests are rejected as the rate limit is exceeded and the request would need to be suspended for longer than `max_delay_seconds`.
However, the 7th request still exceeds the rate limit but reaches the API just less than 20s before it could be successfully processed according to the rate limit.
Thus it is suspended for ~19 seconds and processed afterwards as indicated by the relatively long transaction time.
Request #8 is successfully processed, but  
