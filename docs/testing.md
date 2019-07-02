Testing
-------

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
