# OpenStack Rate Limit Middleware

[![Build Status](https://travis-ci.org/sapcc/openstack-rate-limit-middleware.svg?branch=master)](https://travis-ci.org/sapcc/openstack-rate-limit-middleware) [![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

The OpenStack Rate Limit Middleware enforces rate limits and enables traffic shaping for OpenStack APIs per tuple of

- _target type URI_
- _action_
- _scope_ (project, host address)

It also supports enforcing global and scoped rate limits.
More details can be found in the documentation.

Service-to-service requests (those that carry a valid Keystone-confirmed
service token, as injected by `keystonemiddleware`) can optionally be
bypassed via the `bypass_service_token` option — see
[Bypass for service-to-service requests](docs/configure.md#bypass-for-service-to-service-requests).

## Prerequisites

This middleware requires the classification for OpenStack requests.  
The [openstack-watcher-middleware](https://github.com/sapcc/openstack-watcher-middleware) can be used to classify requests
based on the [DMTF CADF specification](https://www.dmtf.org/standards/cadf).
In terms of rate limiting, a request to an OpenStack service can be described by an _action_, _target type URI_ and its _scope_.

Moreover, this middleware only works with `Python 3` version and
uses `Redis >= 5.0.0` as a backend to store rate limits.

It's better to use `Redis` without persistent storage.

## Rate Limiting Algorithms

This middleware supports two algorithms:

### Sliding Window (default)

The sliding window counts requests within a rolling time window. If the count exceeds the configured
maximum, subsequent requests are either delayed or rejected with a 429 response.

```yaml
rates:
  default:
    account/container:
      - action: update
        limit: 100r/m
```

### Token Bucket (burst control)

The token bucket algorithm limits request **bursts** while preserving the same sustained rate.
Use this when bursty clients cause backend contention (e.g., database lock storms, connection
pool exhaustion).

Enable by adding `,burst=N` to the rate limit string:

```yaml
rates:
  default:
    volumes/volume:
      - action: write
        limit: 100r/m,burst=3
```

This allows at most 3 requests simultaneously while maintaining a sustained rate of 100 requests
per minute (1.667 tokens/second refill). Requests beyond the burst capacity are delayed until a
token becomes available, or rejected with 429 if the delay would exceed `max_sleep_time_seconds`.

Both algorithms can be used together in the same configuration. Endpoints without `,burst=`
use the sliding window; endpoints with `,burst=N` use the token bucket.

## Documentation

- [Installation & WSGI configuration](docs/install.md)
- [How to configure rate limits](docs/configure.md)
- [User guide](docs/user.md)
- [Testing](docs/testing.md)
