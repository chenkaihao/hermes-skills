# 5sim Provider — Integration Notes

## Integration Date
2026-05-28

## API Overview
- **Base URL**: `https://5sim.net/v1/`
- **Auth**: Bearer JWT token (header: `Authorization: Bearer <token>`)
- **Product**: `openai` (also: google, telegram, whatsapp)
- **Country slugs**: `usa`, `canada`, `england`, etc.

## Key Endpoints
```
GET  /v1/user/profile                              → balance, account info
GET  /v1/user/buy/activation/{country}/{op}/{product} → rent number (returns {id, phone, price})
GET  /v1/user/check/{id}                           → order status + sms[] array
GET  /v1/user/cancel/{id}                          → cancel order
GET  /v1/user/finish/{id}                          → complete order
GET  /v1/guest/prices?country={c}&product={p}      → pricing info
```

## SMS Polling
The `sms` field in the check response is an array: `[{code, text, sender, created_at}, ...]`.
Poll every 3 seconds. New SMS detected when `len(sms) > last_count`.

## Provider Code Location
- Implementation: `/root/src/any-auto-register/core/base_sms.py` → `FiveSimProvider` class (after `SmsBowerProvider`)
- Registration: `/root/src/any-auto-register/providers/sms/fivesim.py`
- Factory: `create_sms_provider('fivesim_api', config)` in `base_sms.py`

## Database Configuration
- `provider_definitions`: id=5, driver_type='fivesim_api'
- `provider_settings`: id=5, provider_key='fivesim', auth_json contains JWT token
- Config keys: `fivesim_api_key` (JWT), `sms_country` (default: usa), `sms_service` (default: openai), `fivesim_operator` (default: any)

## CRITICAL LIMITATION
**5sim has ZERO physical (non-virtual) numbers for OpenAI globally.**

Checked all 5sim operators across all countries for `openai` product:
- USA: only `virtual51` ($0.20) and `virtual63` ($0.15)
- Canada: no openai product at all
- England: physical carriers (ee, o2, three, lycamobile) listed but ALL count=0
- Netherlands: only lycamobile with count=0
- Germany/France/Spain/Italy: no physical operators for openai

OpenAI accepts the number format (OTP input field appears after submission) but the SMS code never arrives at virtual numbers. This is the same problem as HeroSMS.

## Viable Use Cases
5sim works for non-OpenAI services that accept virtual numbers:
- Telegram, WhatsApp, Google, etc.

The provider code is production-ready and can be left as a fallback option for these services.

## Test Results (2026-05-28)
- ✅ Balance check: $1.00
- ✅ Buy number (usa/openai): success, phone +19832059930, price $0.1483
- ✅ Check order: status RECEIVED
- ✅ Cancel order: status CANCELED
- ❌ Real ChatGPT registration: number accepted by OpenAI form, but SMS never delivered to 5sim
