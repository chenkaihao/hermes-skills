# Kiro API Modes — Chat vs CodeWhisperer

## Two independent AWS services

| | Q Chat API | CodeWhisperer API |
|---|---|---|
| **Domain** | `q.us-east-1.amazonaws.com` | `codewhisperer.us-east-1.amazonaws.com` |
| **Endpoint** | `/generateAssistantResponse` | `AmazonCodeWhispererService.ListAvailableModels` |
| **Purpose** | Actual AI chat (Kiro IDE sends chat here) | Model listing / IDE metadata |
| **Protocol** | AWS EventStream binary (Smithy) | JSON-RPC style (x-amz-target header) |
| **9Router MITM** | ✅ Intercepted (in TARGET_HOSTS) | ❌ Not intercepted |
| **Account suspension** | May or may not be blocked | Often blocked independently |

## The false-negative pitfall

**CodeWhisperer 403 ≠ Chat API broken.** These are separate AWS service permissions. An account can be suspended from CodeWhisperer while chat still works fine.

Old validation (WRONG):
```python
# Step 3 used CodeWhisperer — gave false negatives
POST codewhisperer.us-east-1.amazonaws.com
X-Amz-Target: AmazonCodeWhispererService.ListAvailableModels
→ 403 "User suspended" ❌  ← BUT CHAT MIGHT STILL WORK
```

Correct validation:
```python
# Step 3 uses actual chat endpoint
POST q.us-east-1.amazonaws.com/generateAssistantResponse
Body: {conversationState: {currentMessage: {userInputMessage: {content: "Hi"}}}}
→ 200 or real error
```

## 2026-05-12 discovery

- 23 Kiro accounts: all CodeWhisperer 403 → all ALSO chat API 403
- The suspension was real — both services blocked simultaneously
- But the test method was still wrong in principle: CodeWhisperer is not a chat test

## 9Router connection test

9Router's health check (`testUtils.js`) also uses CodeWhisperer `ListAvailableModels`. This means 9Router may mark connections as "unavailable" even when chat routing works. The actual chat flow goes through `q.us-east-1.amazonaws.com/generateAssistantResponse` via MITM interception.

## 9Router proxy for Kiro

Kiro connections in 9Router db.json need explicit proxy configuration:
- `connectionProxyUrl`: per-connection proxy URL
- OR `proxyId`: reference to a proxyPool entry

Without this, 9Router makes direct (unproxied) requests to AWS Q API.
