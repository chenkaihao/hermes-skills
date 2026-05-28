# ChatGPT/Codex 账号健康检查流程

导入 9Router 后验证账号是否真正可用的标准流程。

## 核心发现（2026-05-28）

| 项目 | 值 | 来源 |
|------|-----|------|
| Codex OAuth client_id | `app_EMoamEEZ73f0CkXaXp7hrann` | 9Router 源码 `/root/src/9router/src/lib/oauth/constants/oauth.js` |
| OAuth token endpoint | `https://auth.openai.com/oauth/token` | 同上 |
| New API Key 位置 | `/root/new-api/data/one-api.db` → `tokens` 表 | 本次会话发现 |
| New API 端口 | `localhost:3000`（Docker） | nginx 反向代理 |
| 9Router 端口 | `localhost:9000`（Next.js UI） | **非 API**，`/v1/` 路径返回 404 |

## 标准健康检查流程

### Step 1: 直接 OAuth 刷新

```python
import requests

resp = requests.post(
    "https://auth.openai.com/oauth/token",
    json={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",  # Codex CLI client
    },
    headers={"Content-Type": "application/json"},
    timeout=20
)
# 200 = token 有效，已轮换
# 401 = token 过期/已消费/账号被封
```

### Step 2: 真实 Chat API 调用

```python
resp = requests.post(
    "https://api.openai.com/v1/chat/completions",
    json={
        "model": "gpt-5.5",
        "messages": [{"role": "user", "content": "Say hi"}],
        "max_tokens": 10
    },
    headers={"Authorization": f"Bearer {new_access_token}"},
    timeout=30
)
```

### Step 3: 解释结果

| 响应 | 含义 | 处理 |
|------|------|------|
| 200 + choices | ✅ 账号可用 | testStatus="available", backoffLevel=0 |
| 429 quota exceeded | ⚠️ 免费账号正常（无付费 API 额度） | testStatus="available", errorCode=429。Codex 路由用 chatgpt.com 不受影响 |
| 401 invalid_token | ❌ token 无效（可能已被消费） | 重新 OAuth 认证 |
| 403 forbidden | ❌ 账号被封 | testStatus="unavailable", 记录封号原因 |

**关键认知**：`api.openai.com` 返回 429 不意味着账号有问题。免费账号没有 API 额度，但 ChatGPT/Codex 的网页路由 (`chatgpt.com`) 不受此限制。9Router 通过 `chatgpt.com` 路由 Codex 请求时不会遇到 429。

## 通过 New API 路由测试

New API（端口 3000）管理实际的路由。需要 API key 才能调用：

```python
# 获取 API key
import sqlite3
conn = sqlite3.connect('/root/new-api/data/one-api.db')
key = conn.execute("SELECT key FROM tokens WHERE id=1").fetchone()[0]
# 例如: uL6KoYoLALlLfuPnsKtZi91PnjoCjRJZESGYThukUX1EGzyH

# 通过 New API 调用（由 9Router 自动选择连接）
resp = requests.post(
    "http://localhost:3000/v1/chat/completions",
    json={"model": "cx/gpt-5.5", "messages": [...], "max_tokens": 10},
    headers={"Authorization": f"Bearer {key}"},
    timeout=30
)
```

**注意**：New API 路由会**自动选择**一个 Codex 连接，无法指定特定账号测试。如果只测一个账号，用 Step 1+2 的直接 OAuth 方式。

## 9Router 状态更新

验证后更新 `providerConnections`：

```sql
UPDATE providerConnections 
SET data = json_set(data, 
    '$.testStatus', 'available',
    '$.backoffLevel', 0,
    '$.errorCode', 429,        -- 或其他实际错误码
    '$.lastError', '[429]: Free account — no paid API access',
    '$.accessToken', '<new_access_token>',
    '$.refreshToken', '<new_refresh_token>',
    '$.lastUsedAt', '<now>'
),
updatedAt = datetime('now')
WHERE email = 'stephaniejenkins@qhvip.cc';
```

## 发现过程

客户端 ID 在本次会话中通过以下路径发现：
1. 注意到现有的 9Router 连接不存储 `clientId`
2. 搜索 9Router 源码：`grep -r "clientId" /root/src/9router/src/`
3. 找到 `/root/src/9router/src/lib/oauth/constants/oauth.js` 中的 `CODEX_CONFIG`
4. `clientId: "app_EMoamEEZ73f0CkXaXp7hrann"` — Codex CLI 的 OAuth 客户端

之前使用的 `pdlLIX2s...`（截断的 ChatGPT web client_id）导致 `invalid_client` 错误。
