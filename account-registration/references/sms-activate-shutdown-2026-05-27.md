# SMS-Activate Shutdown Confirmation (2026-05-27)

## Verified

Visited sms-activate.org — confirmed shutdown:
- **Heading**: "Сервис SMS-Activate закрыт" (SMS-Activate service is closed)
- **"А где тогда брать номера?"** → links to HeroSMS as successor
- **Warning**: "If you find a service called SMS-Activate, be assured: it's fraud"

## Impact

- SMS-Activate API is permanently unavailable
- HeroSMS is their official successor
- Codebase still has SmsActivateProvider but it won't work
- All SMS traffic must go through HeroSMS or alternative providers

## Reference

Site: https://sms-activate.org
Date: 2025-12-29 (announced shutdown)
