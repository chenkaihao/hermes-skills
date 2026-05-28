# TextVerified SMS Provider Integration

## Overview

TextVerified is the **only confirmed working SMS provider for OpenAI/ChatGPT registration** as of 2026-05-28. It uses real US physical SIM cards (non-VoIP), unlike 5sim/HeroSMS which only have virtual numbers that OpenAI silently rejects.

- Website: https://www.textverified.com
- API v2: `https://www.textverified.com/api/pub/v2/`
- Official Python SDK: `pip install textverified`
- Price: **$0.50** per OpenAI SMS verification
- Account: khchen1985@gmail.com (balance as of 2026-05-28: $2.00)

## Architecture in any-auto-register

```
core/base_sms.py          → TextVerifiedProvider  (~160 lines)
providers/sms/textverified.py  → register_provider("sms", "textverified_api")
create_sms_provider() factory  → textverified/textverified_api branch
```

Database:
- `provider_definitions` id=6, driver_type='textverified_api'
- `provider_settings` id=6, is_default=1 (primary SMS provider)
- `auth_json`: `{"textverified_api_key": "...", "textverified_api_username": "khchen1985@gmail.com"}`

## Critical Installation Note

The any-auto-register service runs under systemd using `/usr/bin/python3` (system Python), NOT the venv. The `textverified` SDK MUST be installed in system Python:

```bash
pip install textverified --break-system-packages
```

Service restart required after installation: `systemctl restart any-auto-register`

## API Authentication Flow

```
POST /api/pub/v2/auth
  Headers: X-API-KEY + X-API-USERNAME
  → {token: "eyJ...", expiresAt: "..."}
  
All subsequent requests:
  Authorization: Bearer {token}
```

## Key API Endpoints

### Create Verification (get phone number)
```python
from textverified import TextVerified, ReservationCapability

tv = TextVerified(api_key=KEY, api_username=USERNAME)
verification = tv.verifications.create(
    service_name='openai',
    capability=ReservationCapability.SMS,
)
# → verification.number = "6184195979"  (US, add +1 prefix)
# → verification.id = "lr_01KSN..."
# → verification.total_cost = 0.5
```

### Poll for SMS code
```python
sms_list = tv.sms.list(to_number=verification.number)
for sms in sms_list:
    code = sms.parsed_code  # Auto-extracted by TextVerified!
    if code:
        return code
```

### Cancel / Report Success
```python
tv.verifications.cancel(verification.id)   # Cancel unused number
tv.verifications.report(verification.id)   # Mark verification successful
```

### Balance check
```python
balance = tv.account.balance  # e.g. 2.0
```

## Provider Implementation Details

`TextVerifiedProvider` in `core/base_sms.py`:

- `get_number(service, country)` → creates verification via SDK, returns `SmsActivation` with phone number (+1 prefix added if missing)
- `get_code(activation_id, timeout=120)` → polls `sms.list()` every 3s, extracts `parsed_code` (with regex fallback on `sms_content`)
- `cancel(activation_id)` → SDK `verifications.cancel()`
- `report_success(activation_id)` → SDK `verifications.report()`
- `get_balance()` → SDK `account.balance`

Service name mapping: `openai` → `openai`, `chatgpt` → `openai`, default → `servicenotlisted`

## Test Results (2026-05-28)

```
[18:01:22] TextVerified renting: +173****9211 (lr_01KSN9JA2T8E9NNVXS1R69RTBK)
[18:01:25] OpenAI accepted number, OTP input appeared
[18:01:27] Waiting for SMS...
[18:01:39] 🔥 CODE RECEIVED: 293701 (12 seconds!)
[18:01:42] Code submitted successfully, verification completed
[18:01:42] ❌ Browser crashed: NS_BINDING_ABORTED (OAuth navigation, not SMS-related)
```

SMS delivery: **12 seconds** — excellent performance.
The subsequent browser crash was a Camoufox/OAuth navigation issue, unrelated to the SMS provider.

## Why Other Providers Fail

| Provider | Issue | Root Cause |
|----------|-------|------------|
| 5sim | OTP input appears but SMS never arrives | Only virtual51/virtual63 operators globally (0 physical carriers). OpenAI silently blocks virtual numbers |
| HeroSMS | Same as 5sim | Only ote/any operators (all virtual). OpenAI silently blocks |
| SMS-Activate | Permanently shut down | Service closed 2025-12-29, website confirms |

The key insight: virtual numbers are accepted by OpenAI's frontend (OTP input appears, no error shown), but the SMS is never actually delivered to virtual operators because OpenAI's SMS gateway filters them. Physical SIM numbers (TextVerified) are required.

## Task Extra Configuration

```json
{
  "extra": {
    "sms_provider": "textverified",
    "sms_service": "openai",
    "mail_provider": "cfworker_admin_api",
    "identity_provider": "mailbox"
  }
}
```
