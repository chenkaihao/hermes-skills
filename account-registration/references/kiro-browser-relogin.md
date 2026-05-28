# Kiro Browser Re-login (2026-05-26)

Re-authenticating Kiro accounts that lost their refreshToken via headed Camoufox browser.

## Prerequisites

- Xvfb running: `DISPLAY=:99`
- Camoufox + Playwright installed in venv
- Account has password in `accounts.password`
- IPRoyal US residential proxy credentials

## Camoufox Proxy Format (CRITICAL)

Camoufox does NOT handle URL-embedded proxy auth. Must split:

```python
# ❌ WRONG — NS_ERROR_PROXY_AUTHENTICATION_FAILED
proxy={"server": "http://user:pass@host:port"}

# ✅ CORRECT
proxy={
    "server": "http://geo.iproyal.com:12321",
    "username": "4GJSsuSsb3vci2UA",
    "password": "4D9N9XyBb0weKTy8_country-us",
}
```

Also: do NOT pass `screen={"maxWidth":1920,...}` — Camoufox expects a Screen() object, not a dict. Omit it.

## Asyncio Conflict

Camoufox uses sync API (`camoufox.sync_api`). The Hermes agent runs in an asyncio event loop. Running sync Camoufox inside the async loop raises "Playwright Sync API inside the asyncio loop".

**Solution**: Run the browser code in a subprocess (separate Python process with no asyncio):

```python
subprocess.run([venv_python, "worker.py", str(account_id)], timeout=300)
```

The worker uses `camoufox.sync_api.Camoufox` with standard `with` context manager.

## Correct OIDC Parameters

| Parameter | Wrong value | Correct value |
|-----------|------------|---------------|
| `issuerUrl` | `https://view.kiro.dev/?region=us-east-1` | `https://view.awsapps.com/start` |
| `scopes` | `["openid","profile","email",...]` | `["codewhisperer:completions","codewhisperer:analysis","codewhisperer:conversations","codewhisperer:transformations","codewhisperer:taskassist"]` |

Using wrong `issuerUrl` → HTTP 400 "Invalid start url provided".

## OIDC Desktop Flow

The `_desktop_idc_flow` in `browser_register.py` (line 297) handles:

1. Start local callback server (random port 18765-18800)
2. Register OIDC client with correct `redirect_uri`
3. Open authorization URL in browser (reuses existing AWS session from login)
4. Handle OTP prompts on auth page
5. Click "Allow" buttons
6. Capture auth code from callback
7. Exchange code for tokens (accessToken + refreshToken)

## OTP Handling

For `@qhvip.cc` emails, OTP is retrieved via CF Worker API:

```python
r = requests.post("https://mail.qhvip.cc/api/messages/latest-otp",
    json={"email": email}, timeout=30)
code = r.json().get("code")
```

## Saving to DB

```python
cur.execute("""
    INSERT INTO account_credentials (account_id, provider_name, key, value, created_at, updated_at)
    VALUES (?,'kiro',?,?,datetime('now'),datetime('now'))
    ON CONFLICT(account_id, provider_name, key) 
    DO UPDATE SET value=excluded.value, updated_at=datetime('now')
""", (aid, key, value))
```

Keys to save: `refreshToken`, `accessToken`, `clientId`, `clientSecret`.

## Full Worker Script

See `scripts/kiro-relogin-worker.py` for the complete subprocess-compatible worker.

## Pitfalls Encountered

1. **`screen` dict → AttributeError**: `'dict' object has no attribute 'is_set'` — caused by passing `screen={"maxWidth":1920}` to Camoufox. Omit `screen` entirely.
2. **Proxy URL auth → NS_ERROR_PROXY_AUTHENTICATION_FAILED** — Camoufox can't parse username:password from proxy URL. Use separate `username`/`password` fields.
3. **Wrong issuerUrl → HTTP 400 "Invalid start url"** — must use `view.awsapps.com/start`, not `view.kiro.dev`.
4. **`/chat` endpoint false positive** — returns HTTP 200 with UnknownOperationException for all requests. Only `generateAssistantResponse` is authoritative.
5. **Async event loop conflict** — sync Camoufox breaks in asyncio context. Isolate in subprocess.
