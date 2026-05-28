# Import Kiro Accounts into 9Router (SQLite)

## When to Use

After validating Kiro accounts and confirming they're operational, import them into 9Router's connection pool for routing.

## 9Router v0.4.31+ Schema

Database: `/root/src/9router-data/db/data.sqlite` (NOT db.json — v0.4.31 migrated to SQLite)

```sql
CREATE TABLE providerConnections (
  id        TEXT PRIMARY KEY,
  provider  TEXT,
  authType  TEXT,
  name      TEXT,
  email     TEXT,
  priority  INTEGER,
  isActive  INTEGER,
  data      TEXT,       -- JSON: {testStatus, accessToken, refreshToken, expiresAt, proxyId, providerSpecificData, ...}
  createdAt TEXT,
  updatedAt TEXT
);

CREATE TABLE proxyPools (
  id         TEXT PRIMARY KEY,
  isActive   INTEGER,
  testStatus TEXT,
  data       TEXT,       -- JSON: {name, proxyUrl, noProxy, type, region, description, ...}
  createdAt  TEXT,
  updatedAt  TEXT
);
```

## Import Procedure

```python
import sqlite3, json, uuid
from datetime import datetime, timezone

# Source: validated accounts JSON (from check_kiro_accounts.py output or 9Router export)
with open("kiro_accounts.json") as f:
    accounts = json.load(f)

db = sqlite3.connect("/root/src/9router-data/db/data.sqlite")
now = datetime.now(timezone.utc).isoformat()

for i, acc in enumerate(accounts):
    conn_id = str(uuid.uuid4())
    
    data = {
        "testStatus": "untested",
        "backoffLevel": 0,
        "accessToken": acc["accessToken"],
        "refreshToken": acc["refreshToken"],
        "expiresAt": acc.get("expiresAt", ""),
        "displayName": acc["email"],
        "proxyId": "iproyal-us-residential",  # ⚠️ Must match active proxy pool ID
        "providerSpecificData": {
            "authMethod": "idc",
            "provider": "BuilderId",
            "region": "us-east-1",
            "clientId": acc["clientId"],
            "clientSecret": acc["clientSecret"],
        },
    }
    
    db.execute(
        """INSERT INTO providerConnections 
           (id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (conn_id, "kiro", "oauth", f"Account {i+1}", acc["email"], i+1, 1,
         json.dumps(data, ensure_ascii=False), now, now)
    )

db.commit()
db.close()

# Restart 9Router
import subprocess
subprocess.run(["systemctl", "restart", "9router"])
```

## Verification

```bash
# Check connections
sqlite3 /root/src/9router-data/db/data.sqlite \
  "SELECT priority, email, json_extract(data, '$.proxyId') FROM providerConnections WHERE provider='kiro' ORDER BY priority"

# Test routing through 9Router
curl -s -X POST http://localhost:9000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"kr/claude-sonnet-4.5","messages":[{"role":"user","content":"hi"}],"max_tokens":5}' \
  --max-time 60

# Check 9Router logs
journalctl -u 9router --no-pager -n 10 | grep -E "KIRO|kr/"
```

## Key Fields

| Field | Value | Notes |
|-------|-------|-------|
| `proxyId` | `"iproyal-us-residential"` | Must match an active `proxyPools` entry |
| `authMethod` | `"idc"` | AWS Builder ID OIDC flow |
| `region` | `"us-east-1"` | Kiro API region |
| `provider` | `"kiro"` | 9Router provider key for Kiro routing |

## Pitfalls

- ⚠️ Old Kiro connections should be deleted before import to avoid duplicates: `DELETE FROM providerConnections WHERE provider='kiro'`
- ⚠️ `proxyId` must reference an existing, active proxy pool — null/empty means unproxied (IP block risk)
- ⚠️ The `data` column stores JSON, not individual columns — use `json_extract()` for queries
- ⚠️ 9Router v0.4.31 ignores `db.json` — all edits must go through SQLite
