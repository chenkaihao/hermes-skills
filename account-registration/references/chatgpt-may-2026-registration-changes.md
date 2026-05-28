# ChatGPT Registration Flow Changes — May 2026

**Date discovered**: 2026-05-21
**Scope**: `platforms/chatgpt/browser_register.py`

## Summary

ChatGPT changed its post-registration flow: after completing the `about_you` form, the page now redirects to `https://platform.openai.com/welcome?step=create` instead of directly issuing the OAuth callback URL (previously a URL containing `code=`).

This broke all three layers of the registration state machine: the about_you submit handler, the page type detector, and the main registration flow.

## Code Changes Applied

All changes are in `/root/src/any-auto-register/platforms/chatgpt/browser_register.py`.

### Fix 1: about_you submit success detection (line ~2899)

**Problem**: `_submit_about_you_via_page` waited 20s for URL to contain `code=`, `chatgpt.com`, or `sign-in-with-chatgpt`. The new `platform.openai.com` URL didn't match, so it returned `ok=False` with "about_you 提交后未跳转".

**Fix**: Added `platform.openai.com` to the success URL patterns:

```python
if "code=" in current_url or "chatgpt.com" in current_url or "sign-in-with-chatgpt" in current_url or "platform.openai.com" in current_url:
    return {"ok": True, "status": 200, "url": current_url, "data": None, "text": ""}
```

### Fix 2: Page type detection (line ~763)

**Problem**: `_infer_page_type` didn't recognize `platform.openai.com/welcome`, returned empty string, causing "未支持的注册状态: page=-".

**Fix**: Added two new page types:

```python
if "platform.openai.com/welcome" in url:
    return "platform_welcome"
if "platform.openai.com" in url:
    return "platform_page"
```

### Fix 3: Main registration flow state machine (line ~3164)

**Problem**: `_browser_registration_flow` raised RuntimeError when encountering `platform_welcome` — it had no handler for it.

**Fix**: Added handler before the "未支持的注册状态" fallback:

```python
if state.get("page_type") in ("platform_welcome", "platform_page", "chatgpt_home"):
    log(f"注册流程完成：账号已创建，当前在 {state.get('page_type')}")
    return state
```

This returns the state (marking registration as complete) so that `_do_codex_oauth` can then be called separately.

### Fix 4: add_phone SMS failure fallthrough (line ~1443)

**Problem**: When `phone_callback` was provided but SMS verification failed, the code did `return None` (exiting OAuth entirely) without trying the skip mechanism.

**Fix**: Changed `return None` to a log message, allowing fallthrough to the skip logic:

```python
except Exception as exc:
    log(f"  短信验证失败，尝试跳过 add_phone: {exc}")
    # (falls through to skip logic below)
```

## Resolved: HeroSMS Phone Verification (Fix 5)

**Problem**: `build_phone_callbacks` in `core/registration/helpers.py` line 97 used `dict(extra)` when no provider definition existed for HeroSMS. The `extra` dict from the task API call (`{"mail_provider": ..., "sms_provider": "herosms", ...}`) didn't contain `herosms_api_key`, so `create_sms_provider("herosms", merged)` failed with "HeroSMS 未配置 API Key".

**Fix**: Always call `resolve_runtime_settings`, which reads from the DB `provider_settings` table:

```python
# Before (line 97)
merged = settings_repo.resolve_runtime_settings("sms", provider_key, extra) if definition else dict(extra)

# After
merged = settings_repo.resolve_runtime_settings("sms", provider_key, extra)
```

**File**: `/root/src/any-auto-register/core/registration/helpers.py`

**Verification**: Successfully registered 1 ChatGPT account with full OAuth + phone verification on 2026-05-21.

## OpenAI Rotating Refresh Tokens

**Critical fact**: Codex/OpenAI uses **one-time-use (rotating) refresh tokens**. Once a refresh token is consumed to get a new access token, the old refresh token is permanently invalidated. Calling the refresh endpoint again returns:

```
HTTP 401: "Your refresh token has already been used to generate a new access token.
Please try signing in again."
```

This means:
- Sharing the same refresh token across multiple 9Router connections will fail — first use kills all others
- 9Router's auto-refresh mechanism consumes the RT; if the new RT isn't saved properly, the account becomes unrecoverable
- The only recovery path is full re-authentication (OAuth flow from scratch)
