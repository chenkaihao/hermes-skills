# Kiro Camoufox Browser Re-login Pitfalls (2026-05-26)

## When you need browser re-login

Kiro accounts without `refreshToken` must go through headed Camoufox OAuth flow to get new credentials. The `_desktop_idc_flow()` function in `browser_register.py` handles the full OIDC flow.

## Pitfalls encountered

### 1. `screen` parameter causes AttributeError

```python
# ❌ BROKEN — `screen={"maxWidth":1920,"maxHeight":1080}` causes:
# AttributeError: 'dict' object has no attribute 'is_set'
with Camoufox(..., screen={"maxWidth":1920,"maxHeight":1080}) as browser:

# ✅ CORRECT — omit screen entirely
with Camoufox(..., os=["windows"]) as browser:
```

### 2. Proxy auth with special characters

IPRoyal password contains `_country-us` suffix. Camoufox can't parse it when embedded in URL:

```python
# ❌ BROKEN — NS_ERROR_PROXY_AUTHENTICATION_FAILED
proxy={"server": "http://user:pass_country-us@geo.iproyal.com:12321"}

# ✅ CORRECT — split username/password
proxy={
    "server": "http://geo.iproyal.com:12321",
    "username": "4GJSsuSsb3vci2UA",
    "password": "4D9N9XyBb0weKTy8_country-us",
}
```

### 3. Wrong `issuerUrl` for OIDC client registration

```python
# ❌ BROKEN — "Invalid start url provided"
"issuerUrl": "https://view.kiro.dev/?region=us-east-1"

# ✅ CORRECT
"issuerUrl": "https://view.awsapps.com/start"
```

### 4. Wrong OIDC scopes

```python
# ❌ BROKEN — generic scopes, won't work
SCOPES = ["openid", "profile", "email", "codewhisperer:conversations"]

# ✅ CORRECT — Kiro-specific scopes from browser_register.py
SCOPES = [
    "codewhisperer:completions",
    "codewhisperer:analysis",
    "codewhisperer:conversations",
    "codewhisperer:transformations",
    "codewhisperer:taskassist",
]
```

### 5. Camoufox API: sync only, must run in subprocess

```python
# Camoufox is synchronous API (not async)
from camoufox.sync_api import Camoufox  # ✅
# NOT: from camoufox import Camoufox    # ❌ won't work with async with

# Must run in isolated subprocess to avoid asyncio loop conflicts
# Worker script receives account_id as argv[1], reads password from DB
```

### 6. mail.qhvip.cc CF Worker outage

As of 2026-05-26, `mail.qhvip.cc` DNS is NXDOMAIN — the CF Worker mail API is completely down. All @qhvip.cc accounts cannot receive OTP codes automatically.

## Working worker script pattern

See `/root/kiro_relogin_worker.py` for a working example that:
- Imports `_desktop_idc_flow` from `platforms.kiro.browser_register`
- Launches Camoufox with split proxy credentials
- Tolerates missing OTP callback (catches RuntimeError, marks `needs_otp=True`)
- Saves credentials to `account_credentials` table via SQLite
