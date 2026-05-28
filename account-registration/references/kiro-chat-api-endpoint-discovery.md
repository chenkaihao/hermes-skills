# Chat API Endpoint Discovery (UPDATED 2026-05-26)

## The Problem

When testing Kiro account availability, endpoints return misleading results:

| Endpoint | Behavior | Correct? |
|----------|----------|----------|
| `q.us-east-1.amazonaws.com/generateAssistantResponse` | Returns 200 with streaming response for valid accounts, 403 "suspended" for banned | ✅ **AUTHORITATIVE** |
| `q.us-east-1.amazonaws.com/chat` | Returns 200 with `UnknownOperationException` for ALL requests | ❌ **FALSE POSITIVE** — 200 status is meaningless |
| `codewhisperer.us-east-1.amazonaws.com/ListAvailableModels` | Returns 403 "temporarily suspended" for valid accounts | ❌ Separate AWS service, independent suspension policy |

## 2026-05-26 Discovery: /chat is a trap

**The `/chat` endpoint returns HTTP 200 for every request**, even with invalid tokens. The body always contains:

```json
{"Output":{"__type":"com.amazon.coral.service#UnknownOperationException","message":"The requested operation is not recognized by the service."},"Version":"1.0"}
```

This caused a false-positive report of 45/45 accounts valid when in reality 0/45 were usable.

**Root cause**: AWS Q service wraps unknown operations in HTTP 200 responses. The status code alone is not sufficient for validation — you MUST inspect the response body.

## The `generateAssistantResponse` endpoint is the authoritative test

This is the endpoint Kiro IDE actually uses to send chat messages. It returns:
- **200** with streaming assistant response content → valid account
- **403** "Your User ID temporarily is suspended" → banned account
- **400** "Improperly formed request" → valid account but wrong request format

```python
r = requests.post(
    "https://q.us-east-1.amazonaws.com/generateAssistantResponse",
    headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "aws-sdk-js/1.0.18",
    },
    json={
        "conversationState": {
            "chatTriggerType": "MANUAL",
            "conversationId": "test-123",
            "currentMessage": {"userInputMessage": {"content": "Hi", "userInputMessageContext": {}}},
            "history": [],
        }
    },
    proxies=proxy,
    impersonate="chrome131",
    timeout=30,
)
```

## 2026-05-25 Run Results (45 accounts)

| Result | Count | Detail |
|--------|-------|--------|
| ✅ Valid (chat OK) | 0 | NONE usable |
| 🚫 Suspended | 25 | Token refresh works but chat 403 "User ID suspended" |
| ❌ Token invalid | 20 | No refreshToken, accessToken expired |

**Previous run (before endpoint fix) falsely reported 45/45 valid** due to `/chat` endpoint trap.

## getUsageLimits: GET vs POST

| Method | Result |
|--------|--------|
| `POST` with `json={}` | HTTP 200 but body = `UnknownOperationException` — silently wrong |
| `GET` | HTTP 200 with real usage data |

Always use **GET**.

## Lesson

1. **Never trust HTTP 200 alone** — AWS Q wraps all unknown operations in 200 + error body
2. **/chat is NOT a valid endpoint** — it was never a real Kiro chat API
3. **generateAssistantResponse is the ONLY authoritative test** for Kiro account validity
4. **Check response body content**, not just status code
