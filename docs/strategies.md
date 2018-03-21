Rate Limit Strategies
=====================

## Local and global rate limits

This middleware distinguishes between local and global rate limits per action and target type URI.

*Local* rate limits: Requests are counted per local scope which might be the initiator host address, project UID, etc. .
If the number of requests per scope, action, target type URI would exceed the configured maximum a rate limit response is sent.

*Global* rate limits: All requests are counted that sent to this backend without paying attention to the scope.
They are meant to protect a backend from more requests than it can handle.
If the number of requests per action, target type URI would exceed the configured maximum a rate limit response is sent. 

## Strategies

This middleware offers rate limit strategies for multiple scenarios as described hereinafter.

## (1) Fixed window strategy

**TLDR**: This strategy is recommended for enforcing a rate limit with a **high ratio of requests per interval**. 

Configuring a rate limit of a number of `n requests` per `t interval` means that a request is allowed every `ts = t/n`.
If the maximum of requests per time window was reached new requests are either queued or rejected with a *RateLimitExceededResponse*.
Each incoming requests in the same scope will increase the queue time until a configurable maximum (`max_sleep_time_seconds`),
 after which an immediate *RateLimitExceededResponse* is sent.
 
Syntax for enforcing a rate limit using the fixed window strategy:
```
limit: <n>r/<unit>

<n>...      number of requests within the interval
<unit>...   unit such as s, m
```

Example configuration:
```
rates:
  account/container:
    - action: update
      limit: 5r/s
    - action: create
      limit: 2r/s
``` 

API configuration for fixed window strategy:
```
# rate limit response is returned if sleep time exceeds this value
max_sleep_time_seconds: <int> (default: 20)

# number of seconds the rate counter can drop
# larger number results in larger spikes but better average
rate_buffer_seconds: <int> (default: 5)
```

**Notes/Limitations**:  
Especially for enforcing rate limits with a very low ratio of requests/interval configuring a reasonable `max_sleep_time_seconds`
 is important to avoid client side timeouts due to a too long queuing in the middleware. 
Example: Configuring rate limit of `1r/m` and `max_sleep_time_seconds=60` would mean the 2nd request could be queued for up to 60s
 (assuming the first request is handled at 0s).
 
Relevant for rate limits in the range of *minutes or more*: 
The number of actual requests can exceed the configured interval by a factor of 2, if requests are coming at the end of a time window and 
    right at the beginning of the next window.
 
## (2) Sliding window strategy

**TLDR**: This strategy is recommended for enforcing rate limits in the range of **requests/minute - day**.

Requests are rate-limited within a configurable interval - a sliding window.
The sliding window is calculated for each incoming request by looking at the past requests within the configured time.
This strategy enables more complex scenarios, for example `2r/m`, `1000r/h`, `100r/15m`, etc. . 

Syntax for enforcing a rate limit using the sliding window strategy: `<n>r/<m><unit>`.
```
limit: <n>r/<m><unit>

<n>...      number of requests within the interval
<m>...      interval factor
<unit>...   unit such as s, m, h, d
```

Example configuration:
```
rates:
  account/container:
    - action: update
      limit: 5r/15m
      strategy: slidingwindow
    - action: read
      limit: 100r/m
      strategy: slidingwindow
``` 
