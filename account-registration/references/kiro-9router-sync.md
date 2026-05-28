# 9Router 同步指南

将验证通过的 Kiro 账号导入 9Router，使其成为可用的 AI 路由连接。

## 前提条件

- 9Router 服务运行中（默认 `http://localhost:9000`）
- 有效 Kiro 账号（已通过三步验证：token 刷新 + 使用量查询 + Chat API 实测）
- 9Router v0.4.31+（使用 SQLite `/root/src/9router-data/db/data.sqlite`）

## 方法一：直接 SQLite 导入（推荐，v0.4.31+）

9Router v0.4.31 迁移到 SQLite 后，`POST /api/accounts/import` API 不可用（返回 404）。**唯一可靠方法是直接写入 SQLite `providerConnections` 表。**

### 数据格式

`providerConnections` 表结构：
```sql
CREATE TABLE providerConnections (
  id TEXT PRIMARY KEY,        -- UUID
  provider TEXT,              -- "kiro"
  authType TEXT,              -- "oauth"
  name TEXT,                  -- 显示名称
  email TEXT,                 -- 邮箱
  priority INTEGER,           -- 优先级（1=最高）
  isActive INTEGER,           -- 1=启用
  data TEXT,                  -- JSON：凭证 + 代理 + 状态
  createdAt TEXT,
  updatedAt TEXT
);
```

`data` JSON 字段必须包含：
```json
{
  "testStatus": "untested",
  "backoffLevel": 0,
  "accessToken": "aoaAAAAA...",
  "refreshToken": "aorAAAAAG...",
  "expiresAt": "2026-05-17T14:25:04.666Z",
  "displayName": "user@example.com",
  "lastUsedAt": null,
  "consecutiveUseCount": 0,
  "proxyId": "iproyal-us-residential",
  "providerSpecificData": {
    "profileArn": null,
    "authMethod": "idc",
    "provider": "BuilderId",
    "region": "us-east-1",
    "clientId": "xxxVzLWVhc3QtMQ",
    "clientSecret": "eyJraW..."
  }
}
```

**关键字段**：
- `proxyId` — 必须设为有效的 proxyPools ID（如 `iproyal-us-residential`），否则请求走直连
- `providerSpecificData.clientId` / `clientSecret` — token 刷新所必需

### 导入脚本（从 9Router JSON 导出）

```bash
python3 << 'PYEOF'
import json, sqlite3, uuid
from datetime import datetime, timezone

# 读取 9Router 导出的 JSON
with open("kiro_accounts_9router.json") as f:
    source = json.load(f)

db = sqlite3.connect("/root/src/9router-data/db/data.sqlite")
now = datetime.now(timezone.utc).isoformat()

# 清除旧 Kiro 连接
db.execute("DELETE FROM providerConnections WHERE provider = 'kiro'")

for i, conn in enumerate(source.get("providerConnections", [])):
    if conn.get("provider") != "kiro":
        continue
    psd = conn.get("providerSpecificData", {})
    data = {
        "testStatus": "untested",
        "backoffLevel": 0,
        "accessToken": conn.get("accessToken", ""),
        "refreshToken": conn.get("refreshToken", ""),
        "expiresAt": conn.get("expiresAt", ""),
        "displayName": conn.get("email", ""),
        "lastUsedAt": None,
        "consecutiveUseCount": 0,
        "proxyId": "iproyal-us-residential",  # ⚠️ 必须指定
        "providerSpecificData": {
            "profileArn": psd.get("profileArn"),
            "authMethod": psd.get("authMethod", "idc"),
            "provider": psd.get("provider", "BuilderId"),
            "region": psd.get("region", "us-east-1"),
            "clientId": psd.get("clientId", ""),
            "clientSecret": psd.get("clientSecret", ""),
        },
    }
    db.execute(
        """INSERT INTO providerConnections
           (id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(uuid.uuid4()), "kiro", "oauth", f"Account {i+1}",
         conn.get("email", ""), i+1, 1, json.dumps(data), conn.get("createdAt", now), now),
    )

db.commit()
print(f"Imported: {db.execute('SELECT COUNT(*) FROM providerConnections WHERE provider=?', ['kiro']).fetchone()[0]}")
db.close()
# systemctl restart 9router
PYEOF
```

### 导入后验证

```bash
# 重启 9Router
systemctl restart 9router

# 验证连接数
python3 -c "
import sqlite3
db = sqlite3.connect('/root/src/9router-data/db/data.sqlite')
kiro = db.execute('SELECT COUNT(*) FROM providerConnections WHERE provider=? AND isActive=1', ['kiro']).fetchone()
print(f'Kiro active: {kiro[0]}')
db.close()
"

# 验证路由可用
curl -s -X POST http://localhost:9000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"kr/claude-sonnet-4.5","messages":[{"role":"user","content":"Hi"}],"max_tokens":10}' \
  --max-time 120
```

## 方法二：check_kiro_accounts.py --sync-to-9router（注意：API 可能不可用）

`check_kiro_accounts.py` 内置 `--sync-to-9router` 参数，但该功能调用 `POST /api/accounts/import`，此 API 在 v0.4.31+ 可能返回 404。优先使用方法一。

## 数据映射

| JSON 导出字段 | 9Router SQLite 字段 | 说明 |
|-------------|-------------------|------|
| accessToken | data.accessToken | OAuth 访问令牌 |
| refreshToken | data.refreshToken | OAuth 刷新令牌 |
| providerSpecificData.clientId | data.providerSpecificData.clientId | OAuth 客户端 ID |
| providerSpecificData.clientSecret | data.providerSpecificData.clientSecret | OAuth 客户端密钥 |
| email | email, data.displayName | 邮箱 |
| — | data.proxyId | 代理池 ID（⚠️ 必须指定） |

## 常见问题

### 导入后 9Router 日志无请求记录

- 确认 `systemctl restart 9router` 已完成
- 检查 `isActive = 1`
- 检查 `proxyId` 是否为有效的代理池 ID

### 导入后 504/500 超时

- **最常见原因：UFW 防火墙阻止 Docker→9Router 通信。** Docker 通过 `172.17.0.1:9000`（docker0 桥接）访问宿主机，需 `ufw allow 9000/tcp`。`curl localhost:9000` 绕过 iptables，不能作为连通性证明。
- 参考 `llm-api-gateway` skill 的 Docker/UFW connectivity 章节

### 代理池 `proxyId` 不生效

- 确认 `proxyPools` 表中该 ID 存在且 `isActive=1`
- 确认代理 URL 格式正确（IPRoyal 需 `_country-us` 后缀）
- 9Router v0.4.31+ 代理池存于 SQLite，编辑 `db.json` 无效

### 账号 token 过期

- 9Router 会在收到 403 时自动刷新 token（从日志可见 `[TOKEN_REFRESH] Successfully refreshed`）
- 如果 `refreshToken` 本身过期（AWS 账号被暂停），无法恢复

## 9Router 数据持久化

9Router v0.4.31+ 使用 SQLite：
```
/root/src/9router-data/db/data.sqlite      ← 主数据库
/root/src/9router-data/db.json              ← 已弃用（存在但不读取）
/root/src/9router-data/db/.migrated-from-json  ← 迁移标记
```

**⚠️ 编辑 `db.json` 无效** — 所有修改必须通过 SQLite。
