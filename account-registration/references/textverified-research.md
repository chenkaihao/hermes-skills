# TextVerified — SMS Provider Research & Integration Plan

## Research Date
2026-05-28

## Why TextVerified
HeroSMS and 5sim both only offer virtual numbers which OpenAI blocks (SMS never delivered).
TextVerified claims **"Real US mobile numbers backed by physical SIMs"** — the first provider found
that explicitly markets physical SIM infrastructure.

## Account Status
- **Username**: `khchen1985@gmail.com`
- **API Key**: `Xbqg9jcytvSk8IkdtgI0LVfu4TwVK05cCivtPXWj6Z1xWVFxe7LxsE3i1LDKIJ`
- **Balance**: $0.00 (needs funding)
- **Auth**: `X-API-KEY` + `X-API-USERNAME` headers → POST `/api/pub/v2/auth` → Bearer token

## API Overview (v2)
- **Base URL**: `https://www.textverified.com`
- **Official SDK**: `pip install textverified` (installed in any-auto-register venv)

### Key Endpoints
```
POST /api/pub/v2/auth                           → Bearer token from X-API-KEY + X-API-USERNAME
GET  /api/pub/v2/account/me                     → balance, username
GET  /api/pub/v2/services?numberType=mobile&reservationType=verification → service list
POST /api/pub/v2/verifications                  → create verification (rent number)
GET  /api/pub/v2/verifications/{id}             → verification details
POST /api/pub/v2/verifications/{id}/cancel      → cancel
POST /api/pub/v2/verifications/{id}/report      → mark success
GET  /api/pub/v2/sms?to={number}                → list SMS messages
```

### Key Data Types
- `NewVerificationRequest`: service_name, capability (SMS/VOICE/SMS_AND_VOICE_COMBO), max_price, area_code_select_option, carrier_select_option
- `VerificationExpanded`: number, id, service_name, state, total_cost, created_at, ends_at
- `Sms`: id, to_value, from_value, sms_content, **parsed_code** (auto-extracted!), created_at
- `NumberType`: MOBILE, VOIP, LANDLINE

### SMS Polling
SDK provides `sms.incoming(data=verification, timeout=120, polling_interval=1.0)` which
yields Sms objects as they arrive. TextVerified auto-parses verification codes into the
`parsed_code` field — no regex needed.

## Service Confirmation
- **`openai` IS in the service list** (verified via SDK call)
- 4303 total services available
- Both SMS and Voice capabilities exist for openai

## Pricing
- **OpenAI SMS verification**: $0.50 per use (confirmed via `vapi.pricing(req)`)
- Credit-based system, not per-activation billing
- Minimum deposit unknown (check website)

## Integration Plan
TextVerifiedProvider would be simpler than FiveSimProvider because:
1. Auto-parsed codes (`Sms.parsed_code`) — no regex extraction needed
2. `sms.incoming()` handles polling with timeout
3. Official SDK handles auth, retries, error handling

### Provider Methods to Implement
```python
class TextVerifiedProvider(BaseSmsProvider):
    auto_report_success_on_code = False
    
    def get_number(self, *, service, country=""):
        v = self.tv.verifications.create(
            NewVerificationRequest(service_name=service, capability=SMS)
        )
        return SmsActivation(activation_id=v.id, phone_number=v.number, ...)
    
    def get_code(self, activation_id, *, timeout=120):
        v = self.tv.verifications.details(activation_id)
        for sms in self.tv.sms.incoming(data=v, timeout=timeout):
            if sms.parsed_code:
                return sms.parsed_code
        return ""
    
    def cancel(self, activation_id):
        return self.tv.verifications.cancel(activation_id)
    
    def report_success(self, activation_id):
        return self.tv.verifications.report(activation_id)
```

## SDK Usage Pattern
```python
from textverified import TextVerified, NewVerificationRequest, ReservationCapability

tv = TextVerified(api_key="...", api_username="khchen1985@gmail.com")

# Create verification
v = tv.verifications.create(
    NewVerificationRequest(
        service_name="openai",
        capability=ReservationCapability.SMS,
    )
)
print(f"Number: {v.number}")

# Wait for SMS
for sms in tv.sms.incoming(data=v, timeout=120):
    print(f"Code: {sms.parsed_code}")

# Mark success
tv.verifications.report(v.id)
```

## Next Steps
1. Fund the account (estimated $10 for 20 OpenAI verifications)
2. Implement TextVerifiedProvider in `core/base_sms.py`
3. Register as `textverified_api` in provider system
4. Run ChatGPT headed registration test with TextVerified numbers
