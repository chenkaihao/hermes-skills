# 5sim Integration (2026-05-28)

## API Summary

- **Auth**: JWT Bearer token
- **Base URL**: `https://5sim.net/v1/`
- **Product**: `openai` (for ChatGPT/OpenAI verification)
- **Country slugs**: `usa`, `canada`, `england`, `netherlands`, `germany`, etc.
- **Operator**: `any` (auto-select), or specific like `virtual63`, `virtual51`

## Key Endpoints

| Action | Method | Path |
|--------|--------|------|
| Profile/Balance | GET | `/v1/user/profile` |
| Buy activation | GET | `/v1/user/buy/activation/{country}/{operator}/{product}` |
| Check order (SMS) | GET | `/v1/user/check/{id}` |
| Cancel order | GET | `/v1/user/cancel/{id}` |
| Finish order | GET | `/v1/user/finish/{id}` |
| Prices | GET | `/v1/guest/prices?country={country}` |
| Products | GET | `/v1/guest/products/{country}/{operator}` |

## Buy Response

```json
{
  "id": 1017404514,
  "phone": "+16501234567",
  "operator": "virtual63",
  "product": "openai",
  "price": 0.1483,
  "status": "RECEIVED",
  "expires": "2026-05-27T17:09:15Z",
  "sms": null,
  "created_at": "2026-05-27T16:49:15Z",
  "country": "usa"
}
```

## Check Response (SMS received)

`sms` array contains received messages:
```json
{
  "sms": [
    {
      "code": "123456",
      "text": "Your OpenAI verification code is: 123456",
      "sender": "OpenAI",
      "created_at": "2026-05-27T16:50:00Z"
    }
  ]
}
```

## Implementation

### `core/base_sms.py` — `FiveSimProvider(BaseSmsProvider)`

- Constructor: `api_key`, `default_service`, `default_country`, `operator`, `proxy`
- `_product(service)` — maps internal name to 5sim product slug (e.g. `openai` → `openai`)
- `_country(country)` — maps ISO code to 5sim country slug (e.g. `us` → `usa`)
- `get_number(service, country)` → `SmsActivation` — buys activation, returns phone + ID
- `get_code(activation_id, timeout)` → `str` — polls `/user/check/{id}` for SMS
- `cancel(activation_id)` → `bool` — cancels via `/user/cancel/{id}`
- `report_success(activation_id)` → `bool` — finishes via `/user/finish/{id}`
- `auto_report_success_on_code = False`
- `mark_send_succeeded/failed`, `mark_code_failed` — lifecycle hooks

### `providers/sms/fivesim.py` — Registration

```python
from core.base_sms import FiveSimProvider
from providers.registry import register_provider
register_provider("sms", "fivesim_api")(FiveSimProvider)
```

### Factory (`create_sms_provider`)

```python
create_sms_provider("fivesim_api", {
    "fivesim_api_key": "<JWT>",
    "sms_service": "openai",
    "sms_country": "usa",
    "fivesim_operator": "any",
})
```

### Database

- `provider_definitions`: id=5, driver_type=fivesim_api
- `provider_settings`: id=5, auth_json={"fivesim_api_key":"<JWT>"}

## ⚠️ Critical Limitation: No Physical Numbers for OpenAI

**Global scan confirmed: 5sim has ZERO physical carrier numbers (count>0) for `openai` in any country.**

Available operators for OpenAI:
| Country | Operators | Type |
|---------|-----------|------|
| USA | virtual51, virtual63 | Virtual only |
| Canada | (none) | No openai product |
| England | virtual26/34/51/52/53/58/59/60/63 | Virtual only; physical (ee/o2/three/lycamobile) all count=0 |

**OpenAI silently blocks virtual numbers** — the phone submission succeeds (OTP input appears), but the SMS verification code never arrives at the virtual number. This is the same limitation as HeroSMS.

### Workaround

5sim works for non-OpenAI services (Telegram, WhatsApp, Google, etc.). For ChatGPT registration, need a provider with physical US numbers — TextVerified identified as promising alternative (see `references/textverified-api-research.md`).
