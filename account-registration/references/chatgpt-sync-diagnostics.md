# 诊断方法详解

## 1. 全量状态对比脚本

```python
import sqlite3, json

AAR_DB = "/root/src/any-auto-register/account_manager.db"
ROUTER_DB = "/root/src/9router-data/db.json"

# 获取所有 ChatGPT 账号
conn = sqlite3.connect(AAR_DB)
cur = conn.cursor()
cur.execute("SELECT id, email FROM accounts WHERE platform='chatgpt' ORDER BY id;")
aar_accounts = {row[1]: row[0] for row in cur.fetchall()}
conn.close()

# 获取 9Router Codex 账号
with open(ROUTER_DB) as f:
    router_data = json.load(f)
router_emails = {c['email'] for c in router_data['providerConnections'] if c['provider']=='codex'}

# 对比
for email in sorted(aar_accounts):
    acc_id = aar_accounts[email]
    in_router = email in router_emails
    print(f"ID:{acc_id} {email} | {'✅ 已导入' if in_router else '❌ 未导入'}")
```

## 2. 凭证字段名检查

**常见问题**：凭证键名可能是 `access_token`（下划线）而非 `accessToken`（驼峰）。

```python
import sqlite3

conn = sqlite3.connect(AAR_DB)
cur = conn.cursor()

# 先查看账号有哪些键
cur.execute("SELECT DISTINCT key FROM account_credentials WHERE account_id = ?", (acc_id,))
keys = [row[0] for row in cur.fetchall()]
print(f"账号凭证键: {keys}")

# 根据实际键名取值
for key in keys:
    cur.execute("SELECT value FROM account_credentials WHERE account_id=? AND key=?", (acc_id, key))
    val = cur.fetchone()
    if val:
        print(f"  {key}: {val[0][:50]}...")

conn.close()
```

## 3. 多源凭证聚合

一个账号可能有多种凭证来源，按优先级检查：

| 优先级 | 键名 | 说明 |
|--------|------|------|
| 1 | `refresh_token` | OAuth 刷新令牌（可获取新 access_token） |
| 2 | `session_token` | 会话令牌（可调用 `/api/auth/session` 刷新） |
| 3 | `access_token` | 访问令牌（直接可用，但可能过期） |
| 4 | `legacy_token` | 旧版令牌（通常不可用） |

## 4. Token 验证方法

### 方法 A：OAuth 端点验证（推荐）

```python
from curl_cffi import requests as cffi_requests

session = cffi_requests.Session(impersonate="chrome120")
resp = session.post(
    "https://auth.openai.com/oauth/token",
    headers={"content-type": "application/x-www-form-urlencoded", "accept": "application/json"},
    data={
        "client_id": OAUTH_CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "redirect_uri": OAUTH_REDIRECT_URI
    },
    timeout=30
)
# 200 = 有效，可获取新 token
```

### 方法 B：直接 API 调用验证

```python
resp = session.get(
    "https://chat.openai.com/backend-api/me",
    headers={"Authorization": f"Bearer {access_token}"},
    timeout=30
)
# 200 = 有效
# 401 = token 失效
# 403 = 账号被封或 Cloudflare 封锁
```

### 方法 C：9Router 连通性验证

```bash
curl -s "http://localhost:9000/v1/models" \
  -H "Authorization: Bearer <9Router的API密钥>"
# 返回模型列表 = 正常
```

## 5. 常见错误码含义

| HTTP 状态 | 含义 | 处理建议 |
|-----------|------|----------|
| 200 | 成功 | 可正常使用 |
| 401 | Token 无效/过期 | 尝试用 refresh_token 刷新 |
| 403 | 账号被封或 Cloudflare 封锁 | 换账号或等待 |
| 429 | 请求过于频繁 | 降低频率，增加延迟 |

## 6. 9Router DB 字段说明

```json
{
  "id": "UUID",
  "provider": "codex",
  "authType": "oauth",
  "name": "Account N",
  "priority": N,
  "isActive": true,
  "accessToken": "...",
  "refreshToken": "...",
  "expiresAt": "ISO8601",
  "email": "user@example.com",
  "displayName": "User Name",
  "testStatus": "active",  // 仅供参考，可能不准
  "lastUsedAt": "ISO8601"  // 实际使用记录更可靠
}
```

## 7. any-auto-register 启动（可选）

同步脚本**不需要** any-auto-register 后端运行，直接读 SQLite。

如需使用 Web UI 或 API：
```bash
cd /root/src/any-auto-register
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 8. 修复流程总结

```
1. 诊断 → 对比 any-auto-register vs 9Router 账号列表
2. 检查凭证 → 查找所有 key/value，记录实际字段名
3. 分类 → 完整凭证 / 仅 access_token / 仅 session_token / 无凭证
4. 修复 → 按可用凭证选择刷新方式（refresh_token → session_token → OAuth 流程）
5. 验证 → 调用 API 确认 token 有效
6. 同步 → 运行 sync_chatgpt_to_9router.py 或手动注入
7. 验证 9Router → 调用 /v1/models 确认连通性
```
