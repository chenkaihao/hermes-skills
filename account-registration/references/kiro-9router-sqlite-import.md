# 9Router SQLite Import (2026-05-17)

9Router v0.4.31+ has **no REST import API** (`/api/import` returns 404). Import accounts by writing directly to the SQLite database.

## Database

```
/root/src/9router-data/db/data.sqlite
```

## providerConnections table schema

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | UUID |
| `provider` | TEXT | `"kiro"` |
| `authType` | TEXT | `"oauth"` |
| `name` | TEXT | Display name (e.g. "Account 1") |
| `email` | TEXT | Account email |
| `priority` | INTEGER | Load-balancing priority (1-based) |
| `isActive` | INTEGER | 1 = enabled |
| `data` | TEXT | JSON blob with tokens, proxyId, providerSpecificData |
| `createdAt` | TEXT | ISO timestamp |
| `updatedAt` | TEXT | ISO timestamp |

## data JSON structure

```json
{
  "testStatus": "untested",
  "backoffLevel": 0,
  "accessToken": "aoaAAAAA...",
  "refreshToken": "aorAAAA...",
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
    "clientId": "...",
    "clientSecret": "eyJraW..."
  }
}
```

## Active proxy pools

```sql
SELECT id, json_extract(data, '$.name') FROM proxyPools WHERE isActive = 1;
```

Current active: `iproyal-us-residential` (IPRoyal 美国家庭宽带, Hillside IL AT&T)

## Import recipe

```python
import sqlite3, json, uuid
from datetime import datetime, timezone

db = sqlite3.connect("/root/src/9router-data/db/data.sqlite")
now = datetime.now(timezone.utc).isoformat()

# Clear existing (optional)
db.execute("DELETE FROM providerConnections WHERE provider = 'kiro'")

for i, account in enumerate(accounts):
    data = json.dumps({
        "testStatus": "untested",
        "backoffLevel": 0,
        "accessToken": account["accessToken"],
        "refreshToken": account["refreshToken"],
        "expiresAt": account.get("expiresAt", ""),
        "displayName": account["email"],
        "proxyId": "iproyal-us-residential",
        "providerSpecificData": {
            "profileArn": None,
            "authMethod": "idc",
            "provider": "BuilderId",
            "region": "us-east-1",
            "clientId": account["clientId"],
            "clientSecret": account["clientSecret"],
        },
    })
    
    db.execute(
        """INSERT INTO providerConnections 
           (id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(uuid.uuid4()), "kiro", "oauth", f"Account {i+1}", 
         account["email"], i+1, 1, data, now, now),
    )

db.commit()
db.close()
```

After import: `systemctl restart 9router`

## Verification

```bash
# Check Kiro connections
sqlite3 /root/src/9router-data/db/data.sqlite \
  "SELECT COUNT(*) FROM providerConnections WHERE provider='kiro'"

# Test chat through 9Router
curl -s -X POST http://localhost:9000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"kr/claude-sonnet-4.5","messages":[{"role":"user","content":"Hi"}],"max_tokens":10}' \
  --max-time 60
```
