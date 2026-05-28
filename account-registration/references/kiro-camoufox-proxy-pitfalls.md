# Camoufox Browser Proxy Pitfalls

## Session: 2026-05-25 Kiro Browser Re-login

### Pitfall 1: Proxy URL format breaks with special characters

**Problem**: IPRoyal proxy passwords contain `_country-us` suffix (e.g., `4D9N9XyBb0weKTy8_country-us`). When passed as a URL string, Camoufox fails with `NS_ERROR_PROXY_AUTHENTICATION_FAILED`.

```python
# ❌ BROKEN — _country-us suffix confuses Camoufox URL parser
proxy = {"server": "http://user:pass_country-us@geo.iproyal.com:12321"}

# ✅ WORKS — separate username/password fields
proxy = {
    "server": "http://geo.iproyal.com:12321",
    "username": "4GJSsuSsb3vci2UA",
    "password": "4D9N9XyBb0weKTy8_country-us",
}
```

**Note**: curl_cffi (for REST API calls) handles the URL format fine. Only Camoufox/Playwright requires the split format.

### Pitfall 2: `screen` parameter causes `is_set` AttributeError

**Problem**: Passing `screen={"maxWidth": 1920, "maxHeight": 1080}` to Camoufox constructor causes:
```
AttributeError: 'dict' object has no attribute 'is_set'
```

This is because Camoufox expects a `Screen()` or `Viewport` object, not a plain dict.

**Fix**: Simply omit the `screen` parameter entirely. Camoufox uses sensible defaults.

```python
# ❌ BROKEN
Camoufox(screen={"maxWidth": 1920, "maxHeight": 1080})

# ✅ WORKS
Camoufox()
```

### Pitfall 3: `geoip=True` requires extra package

**Problem**: Camoufox recommends `geoip=True` when using proxies, but it requires:
```
pip install camoufox[geoip]
```

**Fix**: Omit `geoip=True` unless you have the extra installed. It's not required for normal operation.

### Working Camoufox Configuration

```python
from camoufox.sync_api import Camoufox

with Camoufox(
    headless=False,
    proxy={
        "server": "http://geo.iproyal.com:12321",
        "username": "4GJSsuSsb3vci2UA",
        "password": "4D9N9XyBb0weKTy8_country-us",
    },
    os=["windows"],
) as browser:
    page = browser.new_page()
    page.goto("https://example.com")
```
