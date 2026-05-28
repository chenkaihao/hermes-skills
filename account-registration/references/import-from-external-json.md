# Import Accounts from External JSON Export

Import account credentials from a standalone JSON file (not from any-auto-register) into 9Router's SQLite database.

## When to Use

- You have a JSON export of accounts from another system
- Accounts were registered outside any-auto-register
- Bulk migration from a backup or external source

## JSON Format

The JSON file should have platform keys mapping to arrays of account objects:

```json
{
  "kiro": [
    {
      "name": "Account 1",
      "email": "user@example.com",
      "accessToken": "aoaAAAAA...",
      "refreshToken": "aorAAAAA...",
      "expiresAt": ""
    }
  ],
  "codex": [
    {
      "name": "Account 1",
      "email": "user@example.com",
      "accessToken": "eyJhbG...",
      "refreshToken": "rt_...",
      "expiresAt": "2026-05-22T06:53:37+00:00"
    }
  ]
}
```

## Target: 9Router SQLite

**⚠️ 9Router v0.4.31+ reads from SQLite at runtime, NOT db.json.**

Path: `/root/src/9router-data/db/data.sqlite`
Table: `providerConnections`
Key columns: `id`, `provider`, `name`, `email`, `priority`, `isActive`, `data` (JSON)

The `data` column stores a JSON blob with auth tokens and metadata:
```json
{
  "testStatus": "untested",
  "backoffLevel": 0,
  "accessToken": "...",
  "refreshToken": "...",
  "expiresAt": "1970-01-01T00:00:00.000Z",
  "displayName": "",
  "proxyId": "iproyal-us-residential",
  "lastUsedAt": "",
  "consecutiveUseCount": 0
}
```

## Import Script

```bash
python3 << 'PYEOF'
import json, uuid, sqlite3
from datetime import datetime, timezone

with open('/path/to/export.json') as f:
    export = json.load(f)

conn = sqlite3.connect('/root/src/9router-data/db/data.sqlite')
c = conn.cursor()

# Deduplicate by email
c.execute("SELECT LOWER(email) FROM providerConnections")
existing_emails = set(r[0] for r in c.fetchall() if r[0])

now = datetime.now(timezone.utc).isoformat()

def import_accounts(accounts, provider):
    imported = 0
    skipped = 0
    for acc in accounts:
        email = (acc.get('email') or '').lower()
        if email and email in existing_emails:
            skipped += 1
            continue
        
        uid = str(uuid.uuid4())
        auth_data = json.dumps({
            'testStatus': 'untested',
            'backoffLevel': 0,
            'accessToken': acc.get('accessToken', ''),
            'refreshToken': acc.get('refreshToken', ''),
            'expiresAt': acc.get('expiresAt', '1970-01-01T00:00:00.000Z'),
            'displayName': '',
            'proxyId': 'iproyal-us-residential',
            'lastUsedAt': '',
            'consecutiveUseCount': 0,
        })
        
        c.execute("""
            INSERT INTO providerConnections (id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt)
            VALUES (?, ?, 'oauth', ?, ?, 1, 1, ?, ?, ?)
        """, (uid, provider, acc.get('name', ''), acc.get('email', ''), auth_data, now, now))
        
        if email:
            existing_emails.add(email)
        imported += 1
    return imported, skipped

kiro_i, kiro_s = import_accounts(export.get('kiro', []), 'kiro')
codex_i, codex_s = import_accounts(export.get('codex', []), 'codex')

conn.commit()
print(f'Kiro: {kiro_i} imported, {kiro_s} skipped')
print(f'Codex: {codex_i} imported, {codex_s} skipped')

# Restart 9Router to pick up new connections
import subprocess
subprocess.run(['systemctl', 'restart', '9router'])
PYEOF
```

## ⚠️ Critical Pitfall: Expired Tokens

**Imported accounts may have expired tokens.** After import, 9Router will cycle through them and each will fail:

| Error | Meaning |
|-------|---------|
| `403 bearer token invalid` | accessToken expired |
| `401 Bad credentials` (on refresh) | refreshToken also dead — account is permanently lost |
| `401 Unauthorized` (Codex) | OAuth credentials fully expired |

**Post-import verification:**
```bash
journalctl -u 9router --since "2 min ago" --no-pager | grep -E "ERROR|FAIL|401|403|Bad credentials"
```

If all new accounts fail with token errors, they need re-registration — refresh tokens cannot be recovered.

## ⚠️ Kiro-Specific Pitfall: Missing clientId/clientSecret in providerSpecificData

**Even if tokens are valid** (they work on the original system), Kiro accounts will fail token refresh in 9Router if `providerSpecificData` doesn't include `clientId` and `clientSecret`.

**Symptoms:**
- `accessToken` works initially (one request succeeds)
- Next request: `403 bearer token invalid`
- 9Router tries to refresh → `401 Bad credentials`
- Account gets `modelLocked` and is excluded from rotation

**Why:** AWS OIDC token refresh at `https://oidc.us-east-1.amazonaws.com/token` requires three parameters:
1. `grant_type=refresh_token`
2. `refresh_token=<token>`
3. `client_id=<per-account-unique-id>` ← MISSING in most external exports

**What the export must include:**
```json
{
  "kiro": [{
    "name": "Account 1",
    "email": "user@example.com",
    "accessToken": "aoaAAAAA...",
    "refreshToken": "aorAAAAA...",
    "expiresAt": "",
    "clientId": "TP0u9yYH2G0IDQK6OaYagnVzLWVhc3QtMQ",
    "clientSecret": "eyJraW..."
  }]
}
```

**⚠️ clientId is per-account unique** — each account has its own clientId assigned by AWS during OIDC registration. Using another account's clientId returns `400 invalid_request`. You cannot infer or derive the clientId from other account data.

**Fix if export is missing these fields:**
1. Ask the source to re-export with clientId and clientSecret
2. Or extract from any-auto-register's `account_credentials` table (if accounts exist there):
   ```sql
   SELECT a.email, c.key, c.value
   FROM accounts a
   JOIN account_credentials c ON c.account_id = a.id
   WHERE a.platform = 'kiro' AND c.key IN ('clientId', 'clientSecret')
   ```
3. Then set `providerSpecificData` in the 9Router connection with:
   ```python
   auth_data['providerSpecificData'] = {
       'clientId': client_id,
       'clientSecret': client_secret,
       'authMethod': 'builder-id',
       'provider': 'BuilderId',
       'region': 'us-east-1',
       'proxyPoolId': 'iproyal-us-residential',
   }
   ```

**Contrast with generic expired tokens:** In the generic case, the `refreshToken` itself is expired (server returns 401 regardless of parameters). In this Kiro-specific case, the `refreshToken` IS valid, but the request is malformed because `clientId` is missing — server can't authenticate the refresh call.

## Verification

After import + restart, check 9Router logs for connection counts:
```bash
journalctl -u 9router --since "1 min ago" --no-pager | grep "total connections"
# Expected: kiro | total connections: N, codex | total connections: M
```
