# NVIDIA NIM — any-auto-register Batch Registration Feasibility (2026-05-25)

## Registration Flow Analysis

NVIDIA NIM signup uses `build.nvidia.com`:

1. Enter email → click Next
2. Email OTP verification
3. Set password, name, country
4. API key available at `/settings/api-keys`

## Anti-Bot Observations

- **Next button non-responsive in headless browser**: Tested on 2026-05-25. Entering email and clicking "Next" produced no response — likely client-side JS bot detection
- **No visible captcha**: No ReCAPTCHA/HCaptcha widget detected on signup page
- **Required: headed mode** (Camoufox) for reliable automation

## any-auto-register Plugin Template

Reference: Tavily platform plugin (`platforms/tavily/`) — the cleanest example of email+OTP based registration.

### Files needed

```
platforms/nvidia/
├── __init__.py
├── plugin.py          ← ~100 lines (adapt Tavily template)
├── browser_register.py ← ~150 lines (handle signup flow)
└── core.py            ← ~50 lines (API key extraction)
```

### Registration steps (browser mode)

```python
class NvidiaBrowserRegister:
    def run(self, email, password):
        # Step 1: Navigate to https://build.nvidia.com/settings/api-keys
        # Step 2: Enter email → click Next
        # Step 3: Wait for OTP email → fill OTP
        # Step 4: Fill password + name + country
        # Step 5: Extract API key from /settings/api-keys page
        return {"email": email, "password": password, "api_key": key}
```

## Risks

| Risk | Level | Mitigation |
|------|-------|-----------|
| JS bot detection | Medium | Camoufox headed + proxy rotation |
| Email domain blocking | Low | Use qhvip.cc domain (already working) |
| IP rate limiting | Medium | IPRoyal US proxy per account |
| API key revocation | Low | NVIDIA free tier stable historically |

## Development Estimate

- Time: 2-3 hours
- Complexity: Low (copy Tavily template, swap registration logic)
- Key challenge: anti-bot bypass (Camoufox + proxy)
