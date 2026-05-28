# Kiro Browser Re-login — Pitfalls & Working Configuration

## Overview

When Kiro accounts lose their `refreshToken` (only have expired `accessToken`), browser OAuth re-login via Camoufox is the only recovery path. Codex refresh paths do not apply — Kiro uses AWS Builder ID OIDC, a completely different auth system.

## Quick Start

```bash
cd /root/src/any-auto-register
DISPLAY=:99 .venv/bin/python3 /root/kiro_relogin_worker.py <account_id>
```

Worker reads email/password from DB automatically.

## Camoufox Configuration (Working)

```python
from camoufox.sync_api import Camoufox

with Camoufox(
    headless=False,                                    # MUST be headed for OAuth
    proxy={
        "server": "http://geo.iproyal.com:12321",       # host:port only
        "username": "4GJSsuSsb3vci2UA",                 # separate fields
        "password": "4D9N9XyBb0weKTy8_country-us",      # NOT embedded in URL
    },
    os=["windows"],
) as browser:
    ...
```

## Pitfalls

### 1. proxy.server must NOT contain credentials

❌ `proxy={"server": "http://user:pass@host:12321"}` → `NS_ERROR_PROXY_AUTHENTICATION_FAILED`

✅ Split into `username`/`password` fields. IPRoyal's `_country-us` password suffix breaks URL parsing.

### 2. screen parameter must be Screen object, not dict

❌ `screen={"maxWidth": 1920, "maxHeight": 1080}` → `AttributeError: 'dict' object has no attribute 'is_set'`

✅ Omit `screen` entirely — Camoufox handles viewport automatically.

### 3. geoip=True requires extra package

❌ `geoip=True` → `NotInstalledGeoIPExtra: pip install camoufox[geoip]`

✅ Just omit it. The warning is cosmetic.

### 4. Camoufox is sync-only — must isolate from asyncio

❌ Running inside Hermes' asyncio event loop → `Playwright Sync API inside the asyncio loop`

✅ Run in subprocess: `subprocess.run([venv_python, worker, str(aid)])`

### 5. OIDC issuerUrl: view.awsapps.com/start NOT view.kiro.dev

❌ `"issuerUrl": "https://view.kiro.dev/?region=us-east-1"` → `HTTP 400: Invalid start url provided`

✅ `"issuerUrl": "https://view.awsapps.com/start"` (from any-auto-register `browser_register.py`)

### 6. Scopes must be codewhisperer:* not generic OIDC

❌ `["openid", "profile", "email", "codewhisperer:conversations"]`

✅ `["codewhisperer:completions", "codewhisperer:analysis", "codewhisperer:conversations", "codewhisperer:transformations", "codewhisperer:taskassist"]`

### 7. AWS post-login platform page

After successful login, AWS may redirect to `signin.aws/platform/d-xxxx/login?workflowStateHandle=xxx` — a platform/workflow confirmation page. The worker's page handler looks for:
- "Trust this browser" checkbox + label
- "Remember this browser"
- "Allow access", "Allow", "Authorize", "Continue", "Skip"
- Generic submit buttons

If the page stalls, check the screenshot at `/tmp/kiro_fail_<id>.png`.

### 8. Must kill stale browser processes between tests

Failed workers may leave Camoufox/Chrome processes. Clean with:
```bash
pkill -f kiro_relogin_worker
pkill -f chrome-linux64  # careful: kills openclaw browser too
```

## OIDC Flow

```
1. Register OIDC client: POST oidc.us-east-1.amazonaws.com/client/register
   → returns clientId + clientSecret
   
2. Authorize: browser opens oidc.../authorize?...
   → AWS Builder ID login (email → password → OTP → Trust browser)
   → redirect to 127.0.0.1:18765/oauth/callback?code=...
   
3. Exchange: POST oidc.../token with authorization_code
   → returns accessToken + refreshToken
   
4. Save: INSERT INTO account_credentials (refreshToken, accessToken, clientId, clientSecret)
```

## Credential Storage

```sql
INSERT INTO account_credentials (account_id, provider_name, key, value, created_at, updated_at)
VALUES (?, 'kiro', ?, ?, datetime('now'), datetime('now'))
ON CONFLICT(account_id, provider_name, key) DO UPDATE SET value=excluded.value
```

Keys: `refreshToken`, `accessToken`, `clientId`, `clientSecret`

## Known Limitations

- **20 accounts without refreshToken** (2026-05-26): all have passwords, all are `@qhvip.cc` with CF Worker OTP
- **25 accounts with refreshToken but suspended**: cannot be fixed by re-login — need Kiro support appeal
- **Re-login takes 60-180 seconds per account** (browser launch + OAuth flow + OTP retrieval)
- **Xvfb required**: `DISPLAY=:99` must be set, Xvfb must be running
