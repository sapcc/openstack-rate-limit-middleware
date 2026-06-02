# Token Bucket Rate Limiting — Implementation Spec

**Date:** 2026-06-02  
**Repo:** `sapcc/openstack-rate-limit-middleware`  
**Status:** Draft  
**Context:** [CINDER_API_EXHAUSTION_INVESTIGATION.md](../cinder/CINDER_API_EXHAUSTION_INVESTIGATION.md)

---

## Problem

The existing sliding window algorithm (`redis_sliding_window.lua`) cannot limit request
**bursts**. A project issuing N simultaneous requests at the start of a window sees all
of them pass — the rate limit only fires once the per-window count is exhausted. For
Cinder, this causes 4+ concurrent volume creates from Gardener (k8s CSI) to all hit
`SELECT quota_usages ... FOR UPDATE` simultaneously, creating InnoDB lock contention
that exhausts the ProxySQL connection pool and triggers pod restarts.

The Lua script already flags this as a known gap:

> *"While this works well for rate limiting we need a slightly more advanced lua script
> for shaping the traffic, like allowing burst requests with delayed/not delayed
> execution."*

---

## Goal

Add an **optional** token bucket algorithm alongside the existing sliding window. The
token bucket provides:

- **Burst capacity** — max requests allowed simultaneously (bucket size)
- **Refill rate** — sustained request rate over time
- **Backward compatibility** — existing `Xr/Yt` configs continue to use the sliding
  window unchanged

---

## Design

### Config Syntax

Extend the existing `limit` string with an optional `,burst=N` suffix:

```yaml
# Existing (unchanged) — uses sliding window
volumes/volume:
  - action: write
    limit: 100r/m

# New — uses token bucket
volumes/volume:
  - action: write
    limit: 100r/m,burst=3
```

`burst=N` means:
- Bucket capacity = N (max concurrent requests allowed simultaneously)
- Refill rate = derived from the base rate (100 requests / 60 seconds = 1.667 tokens/s)
- After N requests drain the bucket, subsequent requests are either slept (if
  `retry_after < max_sleep_time_seconds`) or rejected with 429

### Lua Script: `redis_token_bucket.lua`

New file alongside `redis_sliding_window.lua`.

**Redis state** (per key): a Hash with two fields:
- `tokens` — current token count (float)
- `last_refill` — timestamp of last refill (int, nanosecond precision)

**Parameters passed (7 KEYS, matching existing pattern):**
1. `key` — rate limit key (scope + action + target_type_uri)
2. `now` — current timestamp (nanosecond int)
3. `capacity` — bucket size (burst value)
4. `refill_rate` — tokens per clock_accuracy unit
5. `max_sleep_time_seconds` — max time to sleep before 429
6. `clock_accuracy` — clock precision multiplier
7. `ttl_seconds` — key expiry (prevent stale keys accumulating)

**Algorithm:**
```lua
-- 1. Read current state (or initialize to full bucket if new key)
local state = redis.call('hmget', key, 'tokens', 'last_refill')
local tokens = tonumber(state[1]) or capacity
local last_refill = tonumber(state[2]) or now

-- 2. Refill tokens based on elapsed time
local elapsed = now - last_refill
local refill = elapsed * refill_rate
tokens = math.min(capacity, tokens + refill)

-- 3. Try to consume a token
if tokens >= 1 then
    tokens = tokens - 1
    redis.call('hset', key, 'tokens', tokens, 'last_refill', now)
    redis.call('expire', key, ttl_seconds)
    return {math.floor(tokens), -1}   -- allow immediately
end

-- 4. Calculate how long until a token is available
local deficit = 1 - tokens
local retry_after = math.ceil(deficit / refill_rate)

-- 5. Sleep or reject
if retry_after < max_sleep_time_seconds then
    tokens = tokens - 1   -- pre-book the token
    redis.call('hset', key, 'tokens', tokens, 'last_refill', now)
    redis.call('expire', key, ttl_seconds)
    return {math.floor(tokens), retry_after}   -- sleep, then allow
end

-- Rate limit exceeded and sleep would be too long
return {0, retry_after}   -- reject (429)
```

### Python Changes

**`units.py`** — new static method `parse_token_bucket_rate_limit`:

```python
@staticmethod
def parse_token_bucket_rate_limit(value_string):
    """
    Parse token bucket rate limit definition.

    Example:
      '100r/m,burst=3' => (refill_rate=0.02778/clock_unit, capacity=3)

    Returns (refill_rate, capacity) if burst syntax found, else None.
    """
    if ',burst=' not in value_string:
        return None
    rate_part, burst_part = value_string.split(',burst=', 1)
    capacity = int(burst_part)
    max_calls, window_seconds = Units.parse_sliding_window_rate_limit(rate_part)
    refill_rate = max_calls / window_seconds   # tokens per second
    return refill_rate, capacity
```

**`backend.py`** — `RedisBackend.__init__`: load both scripts at startup:

```python
self.__sliding_window_script = common.load_lua_script("redis_sliding_window.lua")
self.__sliding_window_sha = hashlib.sha1(...).hexdigest()

self.__token_bucket_script = common.load_lua_script("redis_token_bucket.lua")
self.__token_bucket_sha = hashlib.sha1(...).hexdigest()
```

**`backend.py`** — `RedisBackend.rate_limit`: detect burst config and route:

```python
def rate_limit(self, scope, action, target_type_uri, max_rate_string):
    key = common.key_func(scope=scope, action=action, target_type_uri=target_type_uri)
    bucket_params = Units.parse_token_bucket_rate_limit(max_rate_string)
    if bucket_params:
        refill_rate, capacity = bucket_params
        return self.__rate_limit_token_bucket(key, refill_rate, capacity, max_rate_string)
    else:
        max_rate, window_seconds = Units.parse_sliding_window_rate_limit(max_rate_string)
        return self.__rate_limit(key, window_seconds, max_rate, max_rate_string)
```

**`backend.py`** — new `__rate_limit_token_bucket` method: same sleep/reject
logic as existing `__rate_limit`, calling the token bucket script via `EVALSHA`.

### Files Changed

| File | Change |
|------|--------|
| `rate_limit/lua/redis_token_bucket.lua` | **New** — token bucket algorithm |
| `rate_limit/units.py` | Add `parse_token_bucket_rate_limit()` |
| `rate_limit/backend.py` | Load both scripts; route on `burst=` presence |
| `rate_limit/tests/test_token_bucket.py` | **New** — unit tests |
| `README.md` | Document `burst=N` syntax |
| `docs/configure.md` | Document token bucket config |

### Files NOT Changed

| File | Why |
|------|-----|
| `rate_limit/rate_limit.py` | Middleware dispatch unchanged — backend handles routing |
| `rate_limit/provider.py` | Passes `max_rate_string` through unchanged |
| `rate_limit/common.py` | Key generation unchanged — same key format |
| `rate_limit/lua/redis_sliding_window.lua` | Untouched — backward compatible |

---

## Backward Compatibility

- Existing `Xr/Yt` configs (no `burst=`) continue using the sliding window unchanged
- New `Xr/Yt,burst=N` configs opt into the token bucket
- Redis state is a Hash (token bucket) vs sorted set (sliding window) — different data
  structures, different key namespaces, no collision possible
- Mixed configs work: some endpoints on sliding window, others on token bucket

---

## Example: Cinder Volume Creates

```yaml
rates:
  default:
    volumes/volume:
      - action: write
        limit: 100r/m,burst=3
```

Behaviour with 4 simultaneous Gardener creates for the same project:

```
Request 1: 2 tokens remain → passes immediately
Request 2: 1 token remains → passes immediately
Request 3: 0 tokens remain → passes (last token)
Request 4: no tokens       → sleeps ~600ms for next refill, then passes

Net: max 3 concurrent SELECT quota_usages ... FOR UPDATE queries
     4th is delayed by ~600ms — no concurrent lock contention
Sustained rate: unchanged at 100r/m (1.667 tokens/s × 60s = 100)
```

---

## Testing Plan

1. **Unit tests** (`test_token_bucket.py`):
   - `parse_token_bucket_rate_limit('100r/m,burst=3')` returns `(1.667, 3)`
   - `parse_token_bucket_rate_limit('100r/m')` returns `None` (no regression)
   - Token consumption decrements correctly
   - Burst exhaustion triggers sleep path
   - Sleep exceeding `max_sleep_time_seconds` triggers 429
   - Tokens refill correctly after idle period
   - Full bucket on new key (first request always passes)

2. **Integration tests** (existing test framework):
   - Mixed sliding window + token bucket configs in same `ratelimit.yaml`
   - Existing test suite passes unchanged (backward compat)
   - Redis Hash keys don't collide with sorted set keys

---

## Deployment

1. Merge to `sapcc/openstack-rate-limit-middleware`
2. Rebuild cinder image (package installed from source at
   `/var/lib/openstack/src/rate-limit-middleware/`)
3. Update `openstack/cinder/templates/etc/_ratelimit.yaml.tpl` in helm-charts:
   ```yaml
   volumes/volume:
     - action: write
       limit: 100r/m,burst=3
   ```
4. Enable `api_rate_limit.enabled: true` in region values
5. Deploy Redis sub-chart (activates automatically with the flag)
6. Roll out to eu-de-2 first, monitor slow query log and ProxySQL errors

---

## Open Questions

1. **Burst value for Cinder:** `burst=3` keeps max concurrent `FOR UPDATE` queries at 3
   per project. Is 3 the right number, or should it be 2 (more conservative) or 5
   (more permissive)? Needs validation against Gardener's typical parallelism.

2. **Limit string vs separate YAML field:** Inline `100r/m,burst=3` keeps it simple and
   backward compatible. A separate `burst: 3` field is more explicit but requires schema
   changes in `provider.py` and the Limes integration.

3. **TTL for token bucket keys:** Suggest `ceil(capacity / refill_rate) * 2` seconds —
   time for a fully drained bucket to refill, doubled for safety. Prevents stale keys
   from holding state indefinitely.

4. **Path 1 as interim:** The shorter-window approach (`3r/3s` in existing sliding
   window) can be deployed immediately while Path 2 is being developed. Both are
   per-project. Path 1 reduces sustained throughput as a side effect (60r/m instead of
   100r/m); Path 2 preserves it.
