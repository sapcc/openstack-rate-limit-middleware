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

## Token Bucket Rate Limiting (Burst Control)

In addition to the sliding window algorithm, this middleware supports an optional **token bucket** algorithm
for controlling request bursts. The token bucket is useful when you need to limit the number of requests
that can be issued simultaneously, while preserving the same sustained rate over time.

### When to use

- You need to limit concurrent requests to prevent database lock contention or connection pool exhaustion
- Bursty clients (e.g., Kubernetes CSI drivers) send many requests in parallel at the start of a window
- You want to allow short bursts but enforce a sustained rate

### Syntax

Add `,burst=N` to an existing rate limit string:

```yaml
rates:
  default:
    <target_type_uri>:
      - action: <action>
        limit: <n>r/<m><t>,burst=<N>
```

Where:
- `<n>r/<m><t>` is the sustained rate (same syntax as sliding window)
- `burst=<N>` is the maximum number of requests allowed simultaneously (bucket capacity)

### How it works

- **Bucket capacity** = N (max requests allowed in a burst)
- **Refill rate** = derived from the base rate (e.g., `100r/m` = 1.667 tokens/second)
- When a request arrives:
  - If tokens are available, one is consumed and the request passes immediately
  - If no tokens are available but the wait is short, the request is suspended (delayed) then allowed
  - If the wait would exceed `max_sleep_time_seconds`, a 429 response is returned

### Example: Cinder volume creates

```yaml
rates:
  default:
    volumes/volume:
      - action: write
        limit: 100r/m,burst=3
```

Behaviour with 4 simultaneous requests for the same project:

| Request | Tokens remaining | Result |
|---------|-----------------|--------|
| 1st | 2 | Passes immediately |
| 2nd | 1 | Passes immediately |
| 3rd | 0 | Passes immediately (last token) |
| 4th | -1 | Sleeps ~600ms for next refill, then passes |

Sustained rate is preserved at 100 requests/minute. Only the burst concurrency is limited to 3.

### Comparison with sliding window

| Feature | Sliding window (`100r/m`) | Token bucket (`100r/m,burst=3`) |
|---------|--------------------------|--------------------------------|
| Sustained rate | 100 requests per minute | 100 requests per minute |
| Burst handling | All 100 can fire at once | Max 3 at once |
| Use case | General rate limiting | Concurrency/burst control |
| Redis data structure | Sorted Set | Hash |

### Mixed configurations

Sliding window and token bucket configs can coexist in the same configuration file.
Endpoints without `,burst=` continue using the sliding window algorithm unchanged.

```yaml
rates:
  default:
    # Sliding window (unchanged behavior)
    account/container:
      - action: read
        limit: 1000r/m

    # Token bucket (burst-controlled)
    volumes/volume:
      - action: write
        limit: 100r/m,burst=3
```

## Black- & Whitelist

This middleware allows configuring a black- and whitelist for certain scopes and keys.  
A `scope` might be an (initiator/target) project UUID or an initiator host address.
A `key` refers to a project specified by name in the format `$projectDomainName/$projectName`.  
If a scope is blacklisted, the middleware immediately returns the configured blacklist response.
Requests in a whitelisted scope are not rate limited.  
Also see the [examples](../etc/).

## Bypass for service-to-service requests

OpenStack services routinely call each other on behalf of a user (for example
Nova calling Cinder to attach a volume). These service-to-service requests
carry a *service token* in addition to the user token. The service token is
validated by `keystonemiddleware` upstream of this middleware (using its
own configurable token cache, so steady-state validation is in-process and
free); the validation result is injected into the WSGI environ as the
`X-Service-Token` and `X-Service-Identity-Status` headers.

When `bypass_service_token` is enabled, this middleware skips rate limiting
for any request whose `X-Service-Identity-Status` header equals `Confirmed`.
The bypassed request is counted under the existing `requests_whitelisted_total`
StatsD metric with an additional `bypass_reason:service_token` tag, so
operators can observe service-to-service traffic separately in dashboards.

Defaults to `false` (off) to preserve backward-compatible behavior; enable
it per service in `paste.ini`:

```ini
[filter:rate-limit]
paste.filter_factory = rate_limit:OpenStackRateLimitMiddleware.factory
service_type = volumev3
backend_host = redis-cinder
backend_port = 6379
config_file = /etc/cinder/rate_limit.yaml

# Skip rate limiting for service-to-service requests carrying a valid
# (Keystone-confirmed) service token.
bypass_service_token = true
```

> **Important:** For this bypass to be safe you **must** also set
> `service_token_roles_required = True` in the `[keystone_authtoken]` section
> of the service's config. Without it, `keystonemiddleware` marks *any* second
> valid token as `X-Service-Identity-Status: Confirmed` — it only verifies that
> the token is valid, not that it belongs to an account with a service role.
> A regular user could then supply two valid user tokens and circumvent rate
> limiting. With `service_token_roles_required = True`, keystonemiddleware
> additionally requires the service token to carry one of the roles listed in
> `service_token_roles`, so only genuine service-to-service traffic is
> confirmed. See the
> [keystonemiddleware documentation](https://docs.openstack.org/keystonemiddleware/latest/middlewarearchitecture.html#service-tokens).

The header contract matches
[`sap-cloud-infrastructure/internal-only-middleware`](https://github.wdf.sap.corp/sap-cloud-infrastructure/internal-only-middleware);
this middleware never validates the token itself, it only inspects the result
already produced by `keystonemiddleware`.

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
