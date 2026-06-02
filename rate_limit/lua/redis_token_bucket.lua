local key, now_int, capacity_int, refill_rate, max_sleep_time_seconds_int, clock_accuracy_int, ttl_seconds_int
key = tostring(KEYS[1])
now_int = tonumber(KEYS[2])
capacity_int = tonumber(KEYS[3])
refill_rate = tonumber(KEYS[4])
max_sleep_time_seconds_int = tonumber(KEYS[5])
clock_accuracy_int = tonumber(KEYS[6])
ttl_seconds_int = tonumber(KEYS[7])

-- Token bucket rate limiting algorithm.
-- Provides burst control: max N concurrent requests, then requests are delayed or rejected.
-- State is stored as a Redis Hash with fields:
--   tokens     - current token count (float, string-encoded)
--   last_refill - timestamp of last refill (int, clock_accuracy precision)

-- 1. Read current state (or initialize to full bucket if new key)
local state = redis.call('hmget', key, 'tokens', 'last_refill')
local tokens = tonumber(state[1]) or capacity_int
local last_refill = tonumber(state[2]) or now_int

-- 2. Refill tokens based on elapsed time
local elapsed = now_int - last_refill
if elapsed > 0 then
    local refill = elapsed * refill_rate
    tokens = math.min(capacity_int, tokens + refill)
end

-- 3. Try to consume a token
if tokens >= 1 then
    tokens = tokens - 1
    redis.call('hset', key, 'tokens', tostring(tokens), 'last_refill', tostring(now_int))
    redis.call('expire', key, ttl_seconds_int)
    return {math.floor(tokens), -1}
end

-- 4. Calculate how long until a token is available (in seconds)
local deficit = 1 - tokens
local retry_after_clock_units = math.ceil(deficit / refill_rate)
local retry_after_seconds = math.ceil(retry_after_clock_units / clock_accuracy_int)

-- 5. Sleep or reject
if retry_after_seconds < max_sleep_time_seconds_int then
    -- Pre-book the token (go negative)
    tokens = tokens - 1
    redis.call('hset', key, 'tokens', tostring(tokens), 'last_refill', tostring(now_int))
    redis.call('expire', key, ttl_seconds_int)
    return {math.floor(tokens), retry_after_seconds}
end

-- Rate limit exceeded and sleep would be too long
return {0, retry_after_seconds}
