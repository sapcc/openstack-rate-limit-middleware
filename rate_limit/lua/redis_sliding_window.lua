local key, lookback_timestamp_max_int, now_int, max_calls_int, window_seconds_int, max_sleep_time_seconds_int, clock_accuracy_int
key = tostring(KEYS[1])
lookback_timestamp_max_int = tonumber(KEYS[2])
now_int = tonumber(KEYS[3])
max_calls_int = tonumber(KEYS[4])
window_seconds_int = tonumber(KEYS[5])
max_sleep_time_seconds_int = tonumber(KEYS[6])
clock_accuracy_int = tonumber(KEYS[7])

-- Rate limit algorithm inspired by https://engineering.classdojo.com/blog/2015/02/06/rolling-rate-limiter
-- While this works well for rate limiting we need a slightly more advanced lua script for shaping the traffic,
-- like allowing burst requests with delayed/not delayed execution.
-- Remove all API calls that are older than the sliding window.
redis.call('zremrangebyscore', key, '-inf', lookback_timestamp_max_int)
-- List of API calls in the current sliding window.
local reqs, remaining, timestamp0, retry_after_seconds
reqs = redis.call('zrange', key, 1, -1)
-- Get number of remaining requests.
remaining = tonumber(max_calls_int - #reqs)

-- Add timestamp of current request if there are remaining requests (aka rate limit not reached).
if remaining > 0 then
    -- Add timestamp if we still have remaining requests.
    redis.call('zadd', key, now_int, now_int)
    -- Reset expiry time for key.
    redis.call('expire', key, window_seconds_int)
    -- Return the number of remaining requests. Retry after not relevant.
    return {remaining, -1}
end

-- Rate limit reached but check if the requests can be suspended.
-- Get timestamp of 1st requests in current window.
timestamp0 = reqs[1]
-- Calculate how long the request would need to be suspended.
retry_after_seconds = tonumber(math.ceil(timestamp0 + window_seconds_int - now_int) / clock_accuracy_int)
-- Can the requests be suspended and processed later?
if (retry_after_seconds < max_sleep_time_seconds_int) and (remaining - 1 >= -max_calls_int) then
    -- Time when requests will actually be executed.
    now_int = tonumber(now_int + (retry_after_seconds * clock_accuracy_int))
    -- Add timestamp to the list.
    redis.call('zadd', key, now_int, now_int)
    -- Reset expiry time for key.
    redis.call('expire', key, window_seconds_int)
    -- Return if the request can be suspended.
    return {remaining -1 , retry_after_seconds}
end

-- Return if no more remaining requests and suspending request not possible.
-- Ensure the 2nd argument (retry_after is greater than max_sleep_time_seconds_int)
return {0, 2 * max_sleep_time_seconds_int}
