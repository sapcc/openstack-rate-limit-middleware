local key, lookback_timestamp_max_int, now_int, max_calls_int, window_seconds_int
key = tostring(KEYS[1])
lookback_timestamp_max_int = tonumber(KEYS[2])
now_int = tonumber(KEYS[3])
max_calls_int = tonumber(KEYS[4])
window_seconds_int = tonumber(KEYS[5])
-- Rate limit algorithm inspired by https://engineering.classdojo.com/blog/2015/02/06/rolling-rate-limiter
-- While this works well for rate limiting we need a slightly more advanced lua script for shaping the traffic,
-- like allowing burst requests with delayed/not delayed execution.
-- Remove all API calls that are older than the sliding window.
redis.call('zremrangebyscore', key, '-inf', lookback_timestamp_max_int)
-- List of API calls during sliding window.
local reqs = redis.call('zrange', key, 0, -1)
local count = 0
for _ in pairs(reqs) do count = count + 1 end
-- Get number of remaining requests.
local remaining = max_calls_int - count
-- Add timestamp of current request if there are remaining requests.
if remaining > 0 then
    -- Add timestamp if we still have remaining requests.
    redis.call('zadd', key, now_int, now_int)
    -- Reset expiry time for key.
    redis.call('expire', key, window_seconds_int)
end
-- Returns the number of remaining requests and the list of timestamps.
return remaining, reqs
