# ChatGPT OAuth Client ID 陷阱

**发现日期**: 2026-05-12 (第二次验证)

## 问题

验证 ChatGPT 账号时，使用错误的 OAuth client_id 会导致所有账号返回 `"Invalid client specified"`，造成"全部账号失效"的假象。

## 正确的 OAuth 参数

any-auto-register 注册 ChatGPT 时使用的 OAuth 客户端：

```python
# from platforms/chatgpt/constants.py
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"      # ← 正确的
OAUTH_REDIRECT_URI = "http://localhost:1455/auth/callback"  # ← 正确的
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
```

## 错误的 OAuth 参数（勿用！）

```python
# ❌ 这是 iOS App 的 client，刷新 web 注册的 token 会返回 "Invalid client specified"
OAUTH_CLIENT_ID = "pdlLIXEutRQoZoYZSzfoKKmTSqYqKnBK"
OAUTH_REDIRECT_URI = "com.openai.chat://auth0.openai.com/ios/com.openai.chat/callback"
```

## 根因

OpenAI 的 refresh_token 绑定到发行它的 client_id。用错 client_id 做 refresh → `"Invalid client specified"`。

## 正确做法

**始终从 any-auto-register 代码导入，不要硬编码**:

```python
import sys
sys.path.insert(0, "/root/src/any-auto-register")
from platforms.chatgpt.constants import OAUTH_CLIENT_ID, OAUTH_REDIRECT_URI, OAUTH_TOKEN_URL
```

## 影响范围

- `chatgpt-account-sync` skill 的验证脚本受此影响
- 任何调用 `auth.openai.com/oauth/token` 刷新 ChatGPT token 的脚本都要用正确的 client_id
- 注册时用的 client 和刷新时用的 client 必须一致
