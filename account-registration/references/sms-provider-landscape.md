# SMS Provider Landscape for OpenAI Registration (2026-05-28)

## Tested: 5sim

- **Integration**: `FiveSimProvider` in `core/base_sms.py`, registered as `fivesim_api`
- **API**: Bearer JWT token, base `https://5sim.net/v1/`
- **Endpoints**: `GET /user/buy/activation/{country}/{operator}/{product}`, `GET /user/check/{id}`, `GET /user/cancel/{id}`, `GET /user/finish/{id}`
- **Pricing**: $0.15/sms for USA openai
- **Test result (2026-05-28)**: Rented US number `+198****0528` (virtual63). OpenAI accepted the number (OTP input appeared). SMS never arrived — waited 3 minutes, timed out. Same for Canada and England. **Global scan: 0 physical operators for openai product in any country.**
- **Verdict**: ❌ Can't receive OpenAI SMS (virtual-only numbers)
- **Suitable for**: Telegram, WhatsApp, Google, non-OpenAI services

## Tested: HeroSMS

- **Integration**: `HeroSmsProvider` in `core/base_sms.py`, registered as `herosms_api`
- **Test result (2026-05-27)**: US (187) ote, CA (36) ote, US Verizon — all fail. OpenAI accepts number format but SMS never arrives at virtual numbers.
- **Verdict**: ❌ Same virtual-number limitation as 5sim
- **Suitable for**: Non-OpenAI services that accept virtual numbers

## Shut Down: SMS-Activate

- **Status**: Permanently closed (announced 2025-12-29)
- **Site**: `sms-activate.org` → "Сервис SMS-Activate закрыт"
- **Successor**: HeroSMS (official recommendation, but same virtual-only issue)
- **Code**: `SmsActivateProvider` still in codebase but non-functional

## Not Yet Tested

### TextVerified
- **URL**: textverified.com
- **Claim**: Real US non-VoIP mobile numbers for SMS verification
- **Status**: Site was accessible in May 2026 session, not yet integrated

### SMSPool
- **URL**: smspool.net
- **Claim**: SMS verification with real numbers
- **Status**: Mentioned as alternative, not yet evaluated

### Physical SIM
- **Option**: Purchase a US mobile SIM card (e.g., T-Mobile prepaid)
- **Pros**: Guaranteed real number, no VoIP flags
- **Cons**: Physical logistics, one number at a time, monthly cost

## Key Insight

OpenAI's SMS verification has a two-layer check:
1. **Format/region check** — happens immediately when phone submitted. Virtual numbers pass this (OTP input appears).
2. **SMS delivery check** — OpenAI sends SMS. Virtual numbers silently fail to receive it. No error returned to the client; the OTP input just sits waiting forever.

This means you can't tell if a number is valid until you wait 2-3 minutes and see if an SMS arrives. Both 5sim and HeroSMS fail at layer 2.
