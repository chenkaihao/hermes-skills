# 9Router 同步快速参考

## 数据库路径

服务器：`/root/src/9router-data/db.json`

## 核心步骤

```python
import json, uuid, base64
from datetime import datetime, timezone

NINE_ROUTER_DB = "/root/src/9router-data/db.json"
with open(NINE_ROUTER_DB, 'r', encoding='utf-8') as f:
    db = json.load(f)

existing = [c for c in db["providerConnections"] if c["provider"] == "codex"]
next_num = 1
while f"Account {next_num}" in {c.get("name") for c in existing}:
    next_num += 1

for acct in valid_accounts:
    # 1. 解码 id_token 获取 email/name
    # 2. 解码 access_token 获取 expires_at
    # 3. 按 email 匹配去重
    # 4. 更新或创建连接
    # 5. 写回 db.json
```

## 连接字段

```python
{
    "id": str(uuid.uuid4()),
    "provider": "codex",
    "authType": "oauth",
    "name": f"Account {next_num}",
    "priority": next_num,
    "isActive": True,
    "accessToken": "...",
    "refreshToken": "...",
    "expiresAt": "2026-05-19T18:34:39+00:00",
    "email": "user@example.com",
    "displayName": "User Name",
    "testStatus": "active",
    "backoffLevel": 0,
}
```

## 注意事项

- `id_token` 解码：`base64.b64decode(payload_b64 + "="*padding)`
- `expiresAt` 从 `access_token` 的 `exp` 字段计算
- 按 email 去重，已存在则只更新 token
- 注入后需重启 9Router 或等待热加载
