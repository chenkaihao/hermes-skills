# Add-Phone Cloudflare Bypass Technique

## Problem

OpenAI's `add-phone/send` and `phone-otp/validate` API endpoints are behind
Cloudflare JS Challenge. The old `_browser_fetch()` approach (browser `fetch()`) 
returns HTTP 400 with empty body `{` — even through residential proxies.

Direct curl confirms CF challenge page (HTTP 403 with JS challenge HTML).

## Root Cause

Browser `fetch()` sends isolated XHR requests without the full browser
context that passed the CF JS Challenge. The `add-phone/send` endpoint has 
stricter CF rules than regular OpenAI pages (login, password, email OTP all
pass CF normally).

## Solution

Replace fetch API calls with native browser form submission via Playwright:

### Step 1: Phone Number Submission

```python
# Find phone input
phone_input = page.locator('input[type="tel"]').first
phone_input.click(click_count=3)  # Select all
phone_input.type(phone_number, delay=80)

# Tab to trigger any onBlur validation, then Enter to submit
page.keyboard.press("Tab")
time.sleep(0.3)
page.keyboard.press("Enter")
```

### Step 2: Wait for OTP Input (SPA Detection)

OpenAI's add-phone page uses SPA pattern — after submission, the OTP code
input appears ON THE SAME PAGE without URL change. Detection:

```python
for i in range(15):  # ~25 seconds max
    # Check URL change first
    if "add-phone" not in str(page.url):
        return  # Navigated away
    
    # Check for OTP input on current page (SPA pattern)
    try:
        otp_input = _find_otp_input(page)  # Multiple selector fallbacks
        return  # OTP input appeared
    except:
        pass
    
    # Check for error messages
    error_el = page.locator('[role="alert"], .text-red-500').first
    if error_el.is_visible():
        raise RuntimeError(f"Rejected: {error_el.text_content()}")
    
    time.sleep(1.5)
```

### Step 3: SMS Code Submission

```python
otp_input = _find_otp_input(page)
otp_input.fill(sms_code)
time.sleep(0.3)

submit_btn = page.locator('button[type="submit"]').first
submit_btn.click()

# Wait for navigation away from add-phone URL
```

### Step 4: Resend support

```python
def _request_openai_resend():
    resend_btn = page.locator(
        'button:has-text("Resend"), button:has-text("Send again")'
    ).first
    resend_btn.click()
```

## What Was Tried (and Failed)

| Approach | Result |
|----------|--------|
| `_browser_fetch(post, /add-phone/send)` | ❌ CF block → 400 + `{` |
| `fill() + click(button)` | ❌ Page didn't respond to button click |
| `fill() + Tab + Enter` + URL-based navigation detection | ❌ SPA doesn't change URL |
| **`fill() + Tab + Enter` + OTP-on-same-page detection** | ✅ **Works** |

## Key Insight

The keyboard `Enter` key on a focused input triggers the **native HTML form
submit event**, which goes through the browser's normal navigation pipeline
and carries all cookies, headers, and CF clearance tokens. JavaScript 
interceptors on the form still fire because `Enter` triggers the same
`submit` event as clicking the button.

## Commits

- `0dff59d` — Initial page-interaction rewrite
- `e168ce5` — Switch to keyboard Enter + OTP-on-same-page detection
- `5572e31` — HeroSMS operator support (separate concern)

## Files Modified

- `platforms/chatgpt/browser_register.py`:
  - `_handle_add_phone_challenge()` — full rewrite
  - `_fill_and_submit_phone()` — new helper
  - `_find_otp_input()` — new helper
