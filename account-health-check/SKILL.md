---
name: account-health-check
description: >
  验证 9Router 中特定账号是否健康可用。两档模式：快速检查（OAuth 刷新 +
  普通 LLM 调用，验证系统链路通畅）和定向检查（隔离目标账号后做 LLM 调用，
  确认该账号本身可用）。禁止用 api.openai.com 付费端点——必须走真实路由链路。
triggers:
  - 健康检查
  - health check
  - 验证账号
  - verify account
  - 测试账号
  - test account
  - 检查 token
---

# Account Health Check — 账号健康检查

## 铁律 ⚠️

1. **禁止用 `api.openai.com`**：那是付费 API 端点，免费账号永远返回 429。必须走真实路由链路。
2. **真实链路**：`New API (3000) → 9Router → IPRoyal 代理 → 上游模型`
3. **必须走真实 LLM 调用**：OAuth 刷新成功 ≠ 账号可用，token 有效 ≠ chat 可用。
4. **定向检查 = 隔离法**：禁用其他同类型连接 → 测试 → 恢复。这是唯一保证测试目标账号的方式。

## 环境常量

| 常量 | 值 |
|------|-----|
| New API 地址 | `http://localhost:3000/v1/chat/completions` |
| New API Key | `uL6KoYoLALlLfuPnsKtZi91PnjoCjRJZESGYThukUX1EGzyH` |
| 9Router DB | `/root/src/9router-data/db/data.sqlite` |
| Codex OAuth client_id | `app_EMoamEEZ73f0CkXaXp7hrann` |
| OAuth token URL | `https://auth.openai.com/oauth/token` |
| Codex 测试模型 | `cx/gpt-5.5` |
| New API 端口 | 3000（Docker 容器，偶尔超时需重试） |

## 模式一：快速检查（验证系统链路）

适用场景：导入新账号后快速确认系统链路通畅（不保证目标账号被选中）。

```python
import requests, time

# Step 1: OAuth 刷新验证
r = requests.post("https://auth.openai.com/oauth/token", json={
    "grant_type": "refresh_token",
    "refresh_token": "<账号的 refresh_token>",
    "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
}, headers={"Content-Type": "application/json"}, timeout=15)

# Step 2: 真实 LLM 调用（走完整链路）
r = requests.post("http://localhost:3000/v1/chat/completions", json={
    "model": "cx/gpt-5.5",
    "messages": [{"role": "user", "content": "Say hello in one word"}],
    "max_tokens": 5,
}, headers={"Authorization": "Bearer uL6KoYoLALlLfuPnsKtZi91PnjoCjRJZESGYThukUX1EGzyH"}, timeout=30)

# 判定：HTTP 200 + choices[0].message.content 非空 = 链路通
```

**注意**：此模式不能保证路由选中目标账号（9Router 轮询所有 active 同类型连接）。

## 模式二：定向检查（隔离验证特定账号）

适用场景：需要确认**特定账号**能处理真实 LLM 请求。

### 流程

```
1. 禁用所有其他同 provider 的 active 连接
2. OAuth 刷新目标账号 token
3. LLM 调用（此时只有目标账号可用）
4. 恢复所有被禁用的连接
5. 提交 git
```

### 脚本

```python
import sqlite3, json, requests, time

TEST_EMAIL = "<目标邮箱>"
DB = "/root/src/9router-data/db/data.sqlite"
NEW_API = "http://localhost:3000/v1/chat/completions"
API_KEY = "uL6KoYoLALlLfuPnsKtZi91PnjoCjRJZESGYThukUX1EGzyH"

conn = sqlite3.connect(DB)
cur = conn.cursor()

# 1. 获取目标账号 ID
cur.execute("SELECT id, data FROM providerConnections WHERE email = ?", (TEST_EMAIL,))
row = cur.fetchone()
test_id, data_str = row
data = json.loads(data_str)
rt = data.get("refreshToken", "")

# 2. 禁用其他 codex 连接
cur.execute("SELECT id, email FROM providerConnections WHERE provider='codex' AND isActive=1 AND id != ?", (test_id,))
others = cur.fetchall()
for cid, email in others:
    conn.execute("UPDATE providerConnections SET isActive = 0 WHERE id = ?", (cid,))
conn.commit()

# 3. OAuth 刷新
r = requests.post("https://auth.openai.com/oauth/token", json={
    "grant_type": "refresh_token", "refresh_token": rt,
    "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
}, headers={"Content-Type": "application/json"}, timeout=15)

if r.status_code == 200:
    tokens = r.json()
    data["accessToken"] = tokens["access_token"]
    if tokens.get("refresh_token"):
        data["refreshToken"] = tokens["refresh_token"]
    data["testStatus"] = "available"
    data["backoffLevel"] = 0
    cur.execute("UPDATE providerConnections SET data = ? WHERE id = ?",
                 (json.dumps(data), test_id))
    conn.commit()

# 4. LLM 调用
r = requests.post(NEW_API, json={
    "model": "cx/gpt-5.5",
    "messages": [{"role": "user", "content": "Say hello in one word"}],
    "max_tokens": 5,
}, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=30)

success = r.status_code == 200 and "choices" in r.json()

# 5. 恢复
for cid, email in others:
    conn.execute("UPDATE providerConnections SET isActive = 1 WHERE id = ?", (cid,))
conn.commit()
conn.close()

if success:
    print(f"🎯 CONFIRMED: {TEST_EMAIL} handles real LLM calls")
else:
    print(f"❌ FAILED: {r.status_code} - {r.text[:200]}")
```

## 结果判定

| OAuth 刷新 | LLM 调用 | 结论 | testStatus |
|-----------|---------|------|------------|
| ✅ 200 | ✅ 200 + 有效回复 | 健康 | `available` |
| ✅ 200 | ❌ 403/401 | token 被标记/账号被封 | `unavailable` |
| ✅ 200 | ❌ 429 | 免费账号额度限制（正常） | `available`（标注429） |
| ❌ 401 | — | refresh_token 失效 | `unavailable` |
| ❌ 超时 | — | 网络/代理问题 | 重试后判断 |

## 结果持久化

检查完成后必须：
1. 更新 9Router SQLite 中的 `testStatus`、`backoffLevel`、token
2. `git add -A && git commit` 到 `/root/src/9router-data`

## 已知陷阱

1. **New API 偶尔超时**（Docker 端口 3000）：重试 2-3 次，间隔 5s
2. **`api.openai.com` 永远返回 429** 对免费账号：不要用这个端点，走真实链路
3. **9Router 不支持 x-connection-id**（chat handler 未实现）：定向检查必须用隔离法
4. **refresh_token 一次性轮换**（OpenAI Auth0 rotation）：刷新后立即持久化新 RT
5. **OAuth client_id 必须正确**：Codex 用 `app_EMoamEEZ73f0CkXaXp7hrann`，不是 ChatGPT web 的 `pdlLIX2s...`
