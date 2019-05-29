User documentation
------------------

The OpenStack rate limit middleware allows controlling the number of incoming requests on global and project level for an OpenStack API. 
Find more details in the [documentation](strategies.md).

The response will indicate if the user was rate limited provide additional information via headers as shown below. 

| Header                  | Description |
|-------------------------|-------------|
| X-RateLimit-Limit       | The limit for the current request in the format `<n>r/<m><t>`. <br> Read: Limit to `n` requests per window `m` <unit>. Valid interval units are `s, m, h, d`. |
| X-RateLimit-Remaining   | The number of remaining requests within the current window. |
| X-RateLimit-Retry-After | How long a client should wait  |
| X-Retry-After           | For compatibility with OpenStack Swift. Same as `X-RateLimit-Retry-After`. |

 
Example when *not* being rate limited:
```bash
curl -i https://$openstackAPI
HTTP/1.1 200 OK
Status: 200 OK
X-RateLimit-Limit: 60r/m
X-RateLimit-Remaining: 59
```

Example when sending too many requests in a given amount of time (sliding window):
```bash
curl -i https://$openstackAPI
HTTP/1.1 429 Too Many Requests
Status: 429 Too Many Requests
X-RateLimit-Limit: 60r/m
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 60
X-Retry-After: 60
```
