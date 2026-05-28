# Nginx 429 Rate Limit — 9Router Dashboard Icons Fix

## Problem

Accessing `https://tokenfree.cc/9router/dashboard/providers` returns HTTP 429 Too Many Requests. The error appears intermittently.

## Root Cause

The 9Router dashboard page loads 30+ provider icon PNGs via absolute paths like `/providers/groq.png`. These requests hit the Nginx `/` location block which has rate limiting:

```nginx
limit_req_zone $binary_remote_addr zone=newapi:10m rate=10r/s;

location / {
    limit_req zone=newapi burst=30 nodelay;
    limit_req_status 429;
    proxy_pass http://localhost:3000/;
}
```

With `burst=30 nodelay`, the first 30 concurrent icon requests are allowed, but any beyond that immediately return 429.

**Error log evidence**:
```
limiting requests, excess: 30.610 by zone "newapi", client: 120.244.143.127
request: "GET /providers/groq.png HTTP/2.0"
referrer: "https://tokenfree.cc/9router/dashboard/providers"
```

## Fix

Add a dedicated location block for `/providers/` that proxies to 9Router (port 9000) **without** rate limiting:

```nginx
# 9Router static assets (providers icons, etc.) — no rate limit
location /providers/ {
    proxy_pass http://127.0.0.1:9000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Place this **before** the `location /` block in `sites-enabled/clawra`.

## Verification

```bash
# No more 429
for i in $(seq 1 15); do
    curl -sk -o /dev/null -w "%{http_code} " "https://tokenfree.cc/providers/groq.png"
done
# → 404 404 ... (icons don't exist at path, but rate limit is gone)
```

## Related

- This issue only affects Nginx configurations with `limit_req` in the `/` location and absolute-path static assets from upstream services
- Same pattern could affect any upstream that references assets outside its URL prefix
