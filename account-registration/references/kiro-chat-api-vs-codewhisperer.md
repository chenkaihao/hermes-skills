# Kiro Chat API vs CodeWhisperer — 关键区分

## 两个独立的 AWS 服务

### 1. Chat API — `q.us-east-1.amazonaws.com`
- **端点**: `POST https://q.us-east-1.amazonaws.com/generateAssistantResponse`
- **功能**: 实际对话。Kiro IDE 发聊天请求走这里。
- **9Router MITM**: 拦截并转发到 `/v1/chat/completions`
- **验证方法**: 发 conversationState 请求，检查 HTTP 200

### 2. CodeWhisperer API — `codewhisperer.us-east-1.amazonaws.com`
- **端点**: `POST https://codewhisperer.us-east-1.amazonaws.com`
- **Target**: `AmazonCodeWhispererService.ListAvailableModels`
- **功能**: 列出模型。不是聊天。
- **谁在用**: 9Router 健康检查
- **9Router MITM**: 不拦截

## 为什么 403 不等于聊天不通

AWS 对这两个服务权限控制独立。账号可能 Chat API 正常但 CodeWhisperer 403。
9Router 健康检查用 CodeWhisperer，所以会把能聊天的账号标 unavailable。

## 验证脚本的正确做法

```python
# 旧：CodeWhisperer（只列模型，经常被封但聊天正常）
POST codewhisperer.us-east-1.amazonaws.com
X-Amz-Target: AmazonCodeWhispererService.ListAvailableModels

# 新：真正 Kiro Chat API
POST q.us-east-1.amazonaws.com/generateAssistantResponse
Body: { conversationState: { currentMessage: { userInputMessage: { content: "Hi" } } } }
```

## 端点汇总

| 端点 | 域名 | 用途 | 9Router 拦截 |
|------|------|------|-------------|
| `/generateAssistantResponse` | `q.us-east-1.amazonaws.com` | 聊天 | MITM |
| `/getUsageLimits` | `q.us-east-1.amazonaws.com` | 额度 | 否 |
| `ListAvailableModels` | `codewhisperer.us-east-1.amazonaws.com` | 模型/健康 | 否 |
| `/token` | `oidc.us-east-1.amazonaws.com` | Token 刷新 | 否 |

## 9Router 代理测试 UI bug

代理池健康检查报 `a.toWellFormed is not a function` 是 9Router 内置 undici 与 Node v22 的兼容 bug。
**不影响实际代理路由**——日志中 `[PROXY]` 正常生效。
