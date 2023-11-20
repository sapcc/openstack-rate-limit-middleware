## Middleware configuration

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

Rate limits can be configured via a _configuration file_ and/or via [_Limes_](https://github.com/sapcc/limes).
The configuration file can only be used to specify global rate limits and defaults for local rate limits,
it also handle the wildcard path configuration.
If scope (project, domain) specific rate limits are required, they have to be set via Limes.
See the [examples](../etc/) for more details.

The syntax for minimal configuration of rate limits is described below.

```yaml
rates:
  <level>:
    <target_type_uri>:
      # The name of the action.
      - action: <action type>

        # Limit to n requests per m <unit>.
        # Valid interval units are `s, m, h, d`.
        limit: <n>r/<m><t>
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
    account/container/*:
      # limit container updates to 10 requests per minute
      - action: update
        limit: 10r/m

      # limit container creations to 5 requests every 10 minutes
      - action: create
        limit: 5r/10m

    # The wildcard configuration can be overridden on specific paths
    account/container/foo_object/something/else:
      - action: update
        limit: 4r/m
      - action: read
        limit: 2r/m
```

## Black- & Whitelist

This middleware allows configuring a black- and whitelist for certain scopes and keys.  
A `scope` might be an (initiator/target) project UUID or an initiator host address.
A `key` refers to a project specified by name in the format `$projectDomainName/$projectName`.  
If a scope is blacklisted, the middleware immediately returns the configured blacklist response.
Requests in a whitelisted scope are not rate limited.  
Also see the [examples](../etc/).

```yaml
# List of blacklisted scopes (project UUID, host address), keys (domainName/projectName).
blacklist:
  - <scope>
  - <key>
  - <username>

# List of blacklisted users by name.
blacklist_users:
  - <userName>

# List of whitelisted scopes (project UUID, host address), keys (domainName/projectName).
whitelist:
  - <scope>
  - <key>

# List of whitelisted users by name.
whitelist_users:
  - <userName>
```

## Whitelist OpenStack Services
This middleware allows to allowlist network communication between OpenStack services. 
If this is not configured, the middleware might rate limit requests between OpenStack services since some of them (e.g. Nova) implement an on behalf mechanism 
passing on the user context. If the service starting the request runs into a rate limit, the customer will receive an HTTP Error 5xx. 
E.g. Customer creating a VM in Nova, Nova calling Neutron for a port creation and runs into a neutron rate limit, does not handle the rate limit and 
returns an HTTP error code 5xx to the customer instead of the rate limit error code.
To avoid this behaviour without rewriting the Openstack Services, this feature can be allowed.

Which IP addresses to allowlist? 
All OpenStack services are running in the same Kubernetes cluster. Withing Kubernetes, POD IPs are assigned based on the nodes podCIDr. 
Futhermore, packets sent to between services from within the cluster are never source NAT'd. 
This is why to allowlist a service, you need to add all the podCIDr of the nodes to the configuration. 
Setting this, all services are whitelisted.

``kubectl get nodes -o jsonpath='{.items[*].spec.podCIDR}'``

''''yaml
openstack_service_ips:
    - <podCIDR>
    - <cidr>
    - <cidr>
''''

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
  body: "<html><body><h1>Rate limit exceeded</h1></body></html>"
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
  body: "<html><body><h1>You have been blacklisted. Contact an administrator.</h1></body></html>"
  # json_body: { "message": "You have been blacklisted. Please contact and administrator." }

  # Optional: Set additional headers.
  headers:
    X-SERVICE: SOMETHING
```
