# Kiro OTP Automation for qhvip.cc Accounts

Discovered 2026-05-12: The CF Worker email API at `mail.qhvip.cc` (historically `temp-email.khchen1985.workers.dev`) manages all `@qhvip.cc` email accounts, enabling automated OTP retrieval during Kiro login.

> ⚠️ **DNS/Worker 故障恢复**：如果 `mail.qhvip.cc` 返回 NXDOMAIN 或 522，按 `references/cfworker-email-recovery.md` 恢复。修复后必须同时更新 `provider_settings` 和所有 `provider_resources` 中的 `api_url`。

## Configuration

**Source**: any-auto-register `provider_settings` table, `provider_key = cfworker_admin_api`

```python
API_URL = "https://temp-email.khchen1985.workers.dev"
ADMIN_TOKEN = "kiro2024!@"
DOMAIN = "qhvip.cc"
```

**Database location**:
```sql
SELECT config_json FROM provider_settings WHERE provider_type='mailbox' AND provider_key='cfworker_admin_api';
-- Returns: {"cfworker_api_url": "https://temp-email.khchen1985.workers.dev", "cfworker_admin_token": "kiro2024!@", "cfworker_domain": "qhvip.cc"}
```

**Programmatic access**:
```python
from infrastructure.provider_settings_repository import ProviderSettingsRepository
settings = ProviderSettingsRepository().resolve_runtime_settings("mailbox", "cfworker_admin_api", {})
api_url = settings.get("cfworker_api_url", "")
admin_token = settings.get("cfworker_admin_token", "")
```

## CF Worker API Endpoints

### GET `/admin/mails` — List emails for an address

```bash
curl -s "https://temp-email.khchen1985.workers.dev/admin/mails?address=calebzhang88@qhvip.cc&limit=10" \
  -H "x-admin-auth: kiro2024!@"
```

Response:
```json
{
  "results": [
    {"id": 273, "subject": "", "from": "", "raw": "..."},
    ...
  ]
}
```

**Fields**:
- `id`: Mail ID (used to track seen emails)
- `subject`: Email subject
- `from`: Sender address
- `raw`: Raw email content (quoted-printable encoded)

## OTP Extraction

AWS verification code emails contain a 6-digit code. Extraction patterns (tried in order):

```python
import re, quopri

def extract_otp(raw_mail: str) -> str | None:
    """Extract 6-digit OTP from raw email content."""
    # Decode quoted-printable
    try:
        decoded = quopri.decodestring(raw_mail.encode()).decode("utf-8", errors="replace")
    except:
        decoded = raw_mail

    patterns = [
        r'验证码[:\uFF1A]\s*(\d{6})',           # Chinese: 验证码：123456
        r'verification code is:?\s*(\d{6})',    # English
        r'Verification code:?\s*(\d{6})',       # English (cased)
        r'>\s*(\d{6})\s*<',                     # HTML tag
        r'\b(\d{6})\b',                         # Generic 6-digit
    ]

    for pat in patterns:
        m = re.search(pat, decoded, re.IGNORECASE)
        if m:
            return m.group(1)
    return None
```

## OTP Callback Pattern

### For KiroBrowserLogin

```python
import requests, re, time, quopri

SEEN_IDS = set()

def otp_callback():
    """Poll CF Worker API for new AWS OTP emails."""
    global SEEN_IDS

    # Record pre-existing emails so we don't use old codes
    if not SEEN_IDS:
        try:
            r = requests.get(
                f"{API_URL}/admin/mails",
                params={"limit": 50, "offset": 0, "address": EMAIL},
                headers={"x-admin-auth": ADMIN_TOKEN},
                timeout=10,
            )
            mails = r.json()
            results = mails.get("results", mails) if isinstance(mails, dict) else mails
            SEEN_IDS.update(str(m.get("id", "")) for m in results if m.get("id"))
        except:
            pass

    start = time.time()
    while time.time() - start < 120:
        try:
            r = requests.get(
                f"{API_URL}/admin/mails",
                params={"limit": 10, "offset": 0, "address": EMAIL},
                headers={"x-admin-auth": ADMIN_TOKEN},
                timeout=10,
            )
            mails = r.json()
            results = mails.get("results", mails) if isinstance(mails, dict) else mails
            for mail in sorted(results, key=lambda x: str(x.get("id", 0)), reverse=True):
                mid = str(mail.get("id", ""))
                if mid in SEEN_IDS:
                    continue
                SEEN_IDS.add(mid)

                raw = mail.get("raw", "")
                try:
                    decoded = quopri.decodestring(raw.encode()).decode("utf-8", errors="replace")
                except:
                    decoded = raw

                for pat in [r'验证码[:\uFF1A]\s*(\d{6})', r'verification code is:?\s*(\d{6})',
                            r'Verification code:?\s*(\d{6})', r'>\s*(\d{6})\s*<', r'\b(\d{6})\b']:
                    m = re.search(pat, decoded, re.IGNORECASE)
                    if m:
                        return m.group(1)
        except Exception as e:
            pass
        time.sleep(3)
    return None  # Timeout

# Usage
from platforms.kiro.browser_register import KiroBrowserLogin

login = KiroBrowserLogin(headless=True, proxy=PROXY, otp_callback=otp_callback)
result = login.run(email, password)
```

### Why protocol login fails

`KiroRegister.login_for_tokens()` does NOT work with this OTP callback. When it submits `EmailOtpRequestInput` to signin execute API, AWS returns HTTP 400:

```
POST signin.aws/api/execute  →  400
{"message": {"text": "Please try signing in again. If the error persists,
 please contact your administrator"}}
```

Only `KiroBrowserLogin` (Camoufox browser automation) successfully completes login with OTP. The browser route uses Desktop OIDC Flow which is more reliable.

## Login Result: What Changes

After successful browser login with OTP:

| Aspect | Before Login | After Login |
|--------|------------|-------------|
| `refreshToken` | Same | Updated (rotated) |
| `accessToken` | Same | New (fresh 1h expiry) |
| `clientId/clientSecret` | Same | New (from Desktop OIDC) |
| `freeTrialInfo.freeTrialStatus` | `None` | **`None` (unchanged)** |
| `baseLimit` | 50 | 50 (unchanged) |
| `totalLimit` | 50 | 50 (unchanged) |

**Conclusion**: Logging in (even with full OTP + Desktop OIDC Flow) does NOT activate freeTrial. The `freeTrialInfo` field is a server-side account attribute set by AWS at account creation time.

## Limitations

- Only works for `@qhvip.cc` email addresses
- Other domains (`hq.accesswiki.net`, `tr.26ai.org`, `qq.com`) are NOT managed by this CF Worker
- CF Worker API has rate limits (unknown threshold)
- `KiroBrowserLogin` requires Camoufox + Playwright (~30MB browser download)
- Each login takes 60-90 seconds (headless browser + OTP polling)
