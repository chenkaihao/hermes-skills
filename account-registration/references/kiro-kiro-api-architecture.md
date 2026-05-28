# Kiro API Architecture: Q Chat vs CodeWhisperer

**Discovered 2026-05-12** — A critical distinction that caused a full day of misdiagnosis.

## Two Separate AWS Services

Kiro (Amazon Q Developer) uses two independent AWS API endpoints:

### 1. Q Chat API — `q.us-east-1.amazonaws.com`

| Attribute | Value |
|-----------|-------|
| **Purpose** | Actual AI chat conversations |
| **Endpoint** | `POST /generateAssistantResponse` |
| **Protocol** | AWS EventStream binary (Smithy framework) |
| **9Router MITM** | ✅ Intercepted — converts to/from OpenAI format |
| **Health check** | Send "Hi", expect valid response |
| **Suspension risk** | Low — this is the primary service |

This is what Kiro IDE uses when you type a message. 9Router's MITM (`src/mitm/handlers/kiro.js`) intercepts requests to this host at `/generateAssistantResponse`, converts the CodeWhisperer-formatted `conversationState` body into OpenAI `messages[]`, forwards to `/v1/chat/completions`, and re-encodes the OpenAI SSE response back into AWS EventStream binary frames.

**Verification command**:
```python
import requests
r = requests.post(
    "https://q.us-east-1.amazonaws.com/chat",
    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
    json={"messages": [{"role": "user", "content": "Hi"}], "maxTokens": 50},
)
# HTTP 200 = account works for chat
```

### 2. CodeWhisperer API — `codewhisperer.us-east-1.amazonaws.com`

| Attribute | Value |
|-----------|-------|
| **Purpose** | Model listing, code completion metadata |
| **Endpoint** | `POST /` with `x-amz-target: AmazonCodeWhispererService.ListAvailableModels` |
| **Protocol** | AWS JSON protocol |
| **9Router MITM** | ❌ Not intercepted — direct AWS passthrough |
| **Health check** | 9Router's connection test uses this |
| **Suspension risk** | High — AWS suspends accounts from this service independently |

9Router uses this for its connection health check (`src/lib/oauth/services/kiro.js:256 listAvailableModels()`). AWS can suspend accounts from CodeWhisperer while leaving Q Chat operational — these are separate permissions.

**403 suspended response**:
```json
{"__type":"com.amazon.aws.codewhisperer#AccessDeniedException",
 "message":"Your User ID (xxx) temporarily is suspended. We've locked your account as a security precaution."}
```

## Why This Matters

| Scenario | Q Chat | CodeWhisperer | 9Router shows |
|----------|--------|---------------|---------------|
| Healthy account | ✅ 200 | ✅ 200 | active |
| Suspended from CW only | ✅ 200 | ❌ 403 | **unavailable** (false negative!) |
| Token expired | ❌ 401 | ❌ 401 | unavailable |

**Key insight**: An account marked "unavailable" in 9Router because of CodeWhisperer 403 is still fully functional for chat. The MITM routes chat requests through `q.us-east-1.amazonaws.com`, which is NOT affected by CodeWhisperer suspensions.

## 9Router MITM Target Hosts

From `src/mitm/config.js`:
```javascript
const TARGET_HOSTS = [
  "q.us-east-1.amazonaws.com",         // ← Kiro chat (intercepted)
  // NOTE: codewhisperer.us-east-1.amazonaws.com is NOT in this list
  // CodeWhisperer traffic goes directly to AWS, not through MITM
];

const URL_PATTERNS = {
  kiro: ["/generateAssistantResponse"],   // ← Only intercepts chat requests
};
```

## Validation Methodology Fix

**Before (wrong)**:
```
Step 3 = CodeWhisperer ListAvailableModels → 403 → account "invalid"
```

**After (correct)**:
```
Step 1 = Token refresh → required
Step 2 = Quota query → required  
Step 3 = CodeWhisperer → INFORMATIVE ONLY (403 ≠ account dead)
Step 4 (optional) = Chat API → authoritative health check
```

**The chat API test is the only test that matters for actual usability.** CodeWhisperer is useful for model discovery but its health status is unrelated to chat functionality.
