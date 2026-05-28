# 9Router SQLite Schema (v0.4.31+)

Database: `/root/src/9router-data/db/data.sqlite`
Migration marker: `/root/src/9router-data/db/.migrated-from-json`

> ⛔ **CRITICAL: SQLite is the live data source. db.json is backup-only.**
> 9Router v0.4.31 reads `providerConnections` from SQLite. Modifying `db.json` has no effect on
> running 9Router. Always update SQLite first, then mirror to `db.json` for backup consistency.
> See 2026-05-23 session: tokens synced to `db.json` appeared to succeed but 9Router still used
> stale tokens from SQLite, causing 401 loops.

## Key Tables

### providerConnections
Stores upstream provider account connections (Kiro, ChatGPT/Codex, etc.)

```
id TEXT PRIMARY KEY          — UUID
provider TEXT                — 'kiro', 'codex', etc.
authType TEXT                — 'oauth'
name TEXT                    — Display name (e.g., email prefix)
email TEXT                   — Account email
priority INTEGER             — Load order (auto-incremented per provider)
isActive INTEGER             — 0 or 1
data TEXT                    — JSON with credentials (see below)
createdAt TEXT               — ISO timestamp
updatedAt TEXT               — ISO timestamp
```

**data JSON structure (Kiro):**
```json
{
  "testStatus": "untested|active|unavailable|error",
  "backoffLevel": 0,
  "accessToken": "aoaAAAAA...",
  "refreshToken": "aorAAAAA...",
  "expiresAt": "1970-01-01T00:00:00.000Z",
  "lastUsedAt": "2026-05-13T17:11:26.949Z",
  "consecutiveUseCount": 1,
  "providerSpecificData": {
    "clientId": "Ixj-jnAp...",
    "clientSecret": "eyJraW...",
    "authMethod": "builder-id",
    "provider": "BuilderId",
    "region": "us-east-1",
    "profileArn": null,
    "proxyPoolId": "uuid-from-proxyPools"
  },
  "lastError": null,
  "errorCode": null,
  "lastErrorAt": null,
  "modelLock_*": "ISO timestamp"   — per-model lockout timestamps
}
```

### proxyPools
Stores outbound proxy configurations.

```
id TEXT PRIMARY KEY          — UUID or custom string
isActive INTEGER             — 0 or 1
testStatus TEXT              — 'untested'|'active'|'error'|'unavailable'
data TEXT                    — JSON with proxy details
createdAt TEXT
updatedAt TEXT
```

**data JSON structure:**
```json
{
  "name": "IPRoyal US Hillside (session 30min)",
  "proxyUrl": "http://user:pass_country-us_city-hillside@geo.iproyal.com:12321",
  "noProxy": "",
  "type": "http",
  "region": "us-hillside",
  "description": "Hillside, US - Sticky session 30min",
  "lastTestedAt": "2026-05-13T17:06:00.000Z",
  "lastError": null
}
```

### proxyPools → providerConnections linkage
The `providerSpecificData.proxyPoolId` field in `providerConnections.data` references `proxyPools.id`. To configure which proxy pool a connection uses, set this field.

## Querying

```sql
-- Active Kiro connections
SELECT id, name, email, priority, isActive,
       json_extract(data, '$.testStatus') as status,
       json_extract(data, '$.providerSpecificData.proxyPoolId') as proxy
FROM providerConnections
WHERE provider = 'kiro' AND isActive = 1
ORDER BY priority;

-- Active proxy pools
SELECT id, json_extract(data, '$.name') as name, testStatus
FROM proxyPools
WHERE isActive = 1;

-- Connections per proxy pool
SELECT json_extract(data, '$.providerSpecificData.proxyPoolId') as pool,
       COUNT(*) as conns
FROM providerConnections
WHERE provider = 'kiro'
GROUP BY pool;
```

## Restart
After modifying the SQLite database, restart 9Router to pick up changes:
```bash
systemctl restart 9router
```
