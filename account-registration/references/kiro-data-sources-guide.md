# Data Sources: any-auto-register vs 9Router

# Data Sources: any-auto-register vs 9Router

**Critical distinction** (discovered 2026-05-12): Kiro account data lives in two separate systems with different account sets and validation results.

| Aspect | any-auto-register | 9Router |
|--------|------------------|---------|
| **Database** | SQLite `account_manager.db` | SQLite `data.sqlite` |
| **Account IDs** | Integer (1, 2, 3...) | UUID (0d8f27b4...) |
| **Source of truth** | Registration records | Router connection pool |
| **Typical count** | 21 accounts | 22 connections |
| **Validation method** | AWS credential check | API endpoint test |
| **Account overlap** | Partial (21 of 22 match by email) |

## ⚠️ Database Migration Trap (2026-05-21)

**9Router v0.4.31 migrated from `db.json` to SQLite.** The `db.json` file still exists but is NO LONGER READ by 9Router. All data is in `/root/src/9router-data/db/data.sqlite`.

**Incorrect (will give stale/wrong data):**
```python
# db.json is dead — 9Router v0.4.31+ does not read it
with open('/root/src/9router-data/db.json') as f:
    db = json.load(f)
conns = db.get('connections', [])  # ← EMPTY in migrated DBs
```

**Correct:**
```python
import sqlite3, json
db = sqlite3.connect('/root/src/9router-data/db/data.sqlite')
cur = db.cursor()
cur.execute("SELECT id, name, isActive, data FROM providerConnections WHERE provider='codex'")
for row in cur.fetchall():
    data = json.loads(row[3])
    status = data.get('testStatus', 'unknown')
    error_code = data.get('errorCode', 0)
    # ... analyze
```

**Symptoms of wrong-store query:**
- `db.json` connections list is empty or has fewer records than expected
- Status counts don't match what the 9Router UI shows
- "34 untested" vs actual 63 dead — massive discrepancy

**Provider-specific data columns (SQLite):**
```sql
-- providerConnections columns: id, provider, authType, name, email, priority, isActive, data(JSON), createdAt, updatedAt
-- proxyPools columns: id, name, proxyUrl, noProxy, type, isActive, region, description, updatedAt, testStatus, data(JSON)
```

### Account Status Diagnosis (Codex-specific, 2026-05-21)

To understand the true state of Codex (or any OAuth provider) accounts in 9Router:

```sql
-- Group by testStatus AND errorCode
SELECT 
    json_extract(data, '$.testStatus') as status,
    json_extract(data, '$.errorCode') as error,
    COUNT(*) as cnt,
    SUM(CASE WHEN json_extract(data, '$.refreshToken') IS NOT NULL 
             AND json_extract(data, '$.refreshToken') != '' THEN 1 ELSE 0 END) as has_rt
FROM providerConnections 
WHERE provider = 'codex'
GROUP BY 1, 2
ORDER BY cnt DESC;
```

**Interpreting results:**

| testStatus | errorCode | Meaning | Action |
|-----------|-----------|---------|--------|
| active | 400 | Working, 400=no error detected | Use as-is |
| unavailable | 429 | Temporarily rate-limited | Wait ~15s-26min for auto-recovery |
| unavailable | 401 | Token expired/broken | Check refreshToken: if present and valid, refresh; if absent or 404 on refresh, account is dead |
| untested | 0 | Never tested | Trigger 9Router health check via UI or API call |

**Key insight**: `testStatus` alone is insufficient — must cross-reference with `errorCode` and `refreshToken` presence. An "unavailable" account with errorCode 429 is temporarily down and will recover. An "unavailable" account with errorCode 401 and no refreshToken is permanently dead.

### refreshToken Validity Test (Codex OAuth)

```python
import requests
resp = requests.post('https://api.openai.com/oauth/token', json={
    'grant_type': 'refresh_token',
    'client_id': 'copilot-windows',  # Codex uses copilot-windows client
    'refresh_token': rt
}, timeout=15)
# HTTP 200 → token refreshed successfully
# HTTP 404 → refreshToken is invalid/dead
# HTTP 401 → client_id mismatch or revoked
```

**⚠️ Shared refreshToken warning**: Multiple accounts may share the same refreshToken (e.g., batch-registered from same OAuth session). One failure kills all accounts sharing that RT. Check uniqueness:
```sql
SELECT json_extract(data, '$.refreshToken') as rt, COUNT(*) as cnt
FROM providerConnections WHERE provider = 'codex'
AND json_extract(data, '$.refreshToken') != ''
GROUP BY rt HAVING cnt > 1;
```

## When to Use Which

### any-auto-register DB
```bash
python scripts/check_kiro_accounts.py --db /root/src/any-auto-register/account_manager.db
```

Use cases:
- Validate registration credentials (refreshToken, clientId/secret)
- Audit account registration health
- Find accounts needing re-registration
- Bulk credential verification

### 9Router DB
```bash
python scripts/check_kiro_accounts.py --9router-url http://localhost:9000  # if --sync-to-9router is implemented
```

Use cases:
- Validate active routing connections
- Check which accounts are currently enabled in the router
- Monitor live traffic health
- Production readiness checks

## Key Finding: Divergent Results (2026-05-12)

**Historical test** (2026-05-12 01:43):
- 9Router data: 22/22 valid (100%) via home broadband proxy
- Method: Direct API chat test through 9Router

**Current test** (2026-05-12 01:54):
- any-auto-register data: 9/21 valid (42.9%) via AWS credential check
- Method: Token refresh + Q API + CodeWhisperer ListAvailableModels

**Reasons for difference:**
1. **Different account sets** — 9Router includes Account 7 (no email) missing from any-auto-register
2. **Different test logic** — 9Router tests actual chat API; AWS credential test checks token validity and quota
3. **Timing** — accounts can be suspended between tests (11 minute gap)

## Best Practices

1. **Run both data sources** and compare results
2. **Use 9Router for production readiness** — tests actual API functionality
3. **Use any-auto-register for credential audit** — validates stored credentials
4. **Track changes over time** — account status is not static

## Account Mapping

To map accounts between systems, match by email:

```python
import json, sqlite3

# 9Router connections
with open('/root/src/9router-data/db.json') as f:
    router_conns = [c for c in json.load(f)['providerConnections'] if c['provider']=='kiro']
router_emails = {c['email']: c for c in router_conns}

# any-auto-register accounts
conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
cursor = conn.cursor()
cursor.execute("SELECT id, email FROM accounts WHERE platform='kiro'")
db_emails = {email: acc_id for acc_id, email in cursor.fetchall()}
conn.close()

# Overlap
common = set(router_emails.keys()) & set(db_emails.keys())
print(f"Common emails: {len(common)} / Router: {len(router_emails)} / DB: {len(db_emails)}")
```
