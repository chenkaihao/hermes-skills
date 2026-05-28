# Proxy Configuration & Verification

**Last updated**: 2026-05-15 (IPRoyal recharged, session-specific config deployed)

## IPRoyal Proxy Parameter Syntax

IPRoyal uses the password field for routing parameters:

```
http://user:PASSWORD_country-us_city-HILLSIDE_session-XXXX_lifetime-30m@geo.iproyal.com:12321
```

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `country-us` | Always required | US exit node (without this, routes to SA/DZ) |
| `city-hillside` | Hillside, Illinois | Target city for residential IP |
| `session-XXXX` | Random alphanumeric | Sticky session — same IP for lifetime |
| `lifetime-30m` | 30 minutes | Session duration before IP rotation |

**Current config** (2026-05-15):
```
http://4GJSsuSsb3vci2UA:4D9N9XyBb0weKTy8_country-us_city-hillside_session-9ZySUn49_lifetime-30m@geo.iproyal.com:12321
```
- **出口 IP**: 99.103.40.6 (Hillside, Illinois, US)
- **ISP**: AT&T Enterprises (genuine residential broadband)
- **AS**: AS7018

## All 7 Configuration Locations (Proxy Switch Checklist)

When switching IPRoyal proxy (recharge, new session, rotation), update ALL of these:

| # | Location | File | Field to Update |
|---|----------|------|-----------------|
| 1 | **9Router proxy pool** | `/root/src/9router-data/db/data.sqlite` | `proxyPools` table `data` JSON column. SQL: `json_set(data, '$.proxyUrl', '<new>')` |
| 2 | **9Router .env (main)** | `/root/src/9router/.env` | `http_proxy`, `https_proxy`, `all_proxy` |
| 3 | **9Router .env (standalone)** | `/root/src/9router/.next/standalone/9router/.env` | `http_proxy`, `https_proxy`, `all_proxy` |
| 4 | **any-auto-register DB** | `/root/src/any-auto-register/account_manager.db` | `proxies` table `url` column (id=3, is_active=1) |
| 5 | **Validation skill script** | `/root/.hermes/skills/automation/kiro-account-validation/scripts/check_kiro_accounts.py` | `PROXY_CONFIG` dict |
| 6 | **Batch registration script** | `/root/.hermes/scripts/auto_register_batch.py` | `PROXY_URL` constant |
| 7 | **Legacy check script** | `/root/kiro_account_check.py` | `PROXY_CONFIG` dict |

**After updating**: `systemctl daemon-reload && systemctl restart 9router && systemctl restart import-tool`

**Note**: `import-tool/server.py` does NOT need updates — it references `proxyId: iproyal-us-residential` which draws from location #1.

**Verify with**:
```bash
# 1. Check proxy exit IP
curl -s -x http://4GJSsuSsb3vci2UA:4D9N9XyBb0weKTy8_country-us_city-hillside_session-9ZySUn49_lifetime-30m@geo.iproyal.com:12321 -L https://ipv4.icanhazip.com

# 2. Check IP geolocation
curl -s http://ip-api.com/json/$(curl -s -x http://... -L https://ipv4.icanhazip.com)

# 3. Test 9Router Kiro routing
curl -s -X POST http://localhost:9000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test" \
  -d '{"model":"kr/claude-sonnet-4.5","messages":[{"role":"user","content":"hi"}],"max_tokens":5}' \
  --max-time 30

# 4. Verify 9Router proxy pool (SQLite)
python3 -c "
import sqlite3, json
conn = sqlite3.connect('/root/src/9router-data/db/data.sqlite')
for r in conn.execute('SELECT id, isActive, testStatus, data FROM proxyPools'):
    d = json.loads(r[3])
    print(f'{d[\"name\"]}: {d[\"proxyUrl\"][:80]}... active={r[1]}')
"
```

## Verify Proxy Is Actually Used

### Step 1: Check Direct IP (No Proxy)

```python
import requests
r = requests.get("https://ipinfo.io/json", timeout=10)
print(f"Direct IP: {r.json().get('ip')}")
```

### Step 2: Check Through Proxy

```bash
curl -s -x http://4GJSsuSsb3vci2UA:4D9N9XyBb0weKTy8_country-us_city-hillside_session-9ZySUn49_lifetime-30m@geo.iproyal.com:12321 -L https://ipinfo.io/json
```

Proxy IP should differ from direct IP and resolve to US (AT&T/Comcast/Spectrum, not datacenter ASNs).

### Step 3: Check 9Router Service Environment

```bash
systemctl show 9router --property=Environment | tr ' ' '\n' | grep proxy
```

Look for `http_proxy=`, `https_proxy=` lines with the current IPRoyal config.

### Step 4: Check 9Router Database Proxy Config (SQLite)

```python
import sqlite3, json
conn = sqlite3.connect('/root/src/9router-data/db/data.sqlite')
# Proxy pool entries
for r in conn.execute('SELECT id, isActive, testStatus, data FROM proxyPools'):
    d = json.loads(r[3])
    print(f"  Pool: {d.get('name')} -> {d.get('proxyUrl', '')[:100]}...")
    print(f"  Active: {r[1]}, Test: {r[2]}")
# Connections referencing proxyId
for r in conn.execute('SELECT name, provider, data FROM providerConnections'):
    d = json.loads(r[2])
    pid = d.get('proxyId') or (d.get('providerSpecificData') or {}).get('proxyPoolId')
    if pid:
        print(f"  {r[0]} ({r[1]}) -> proxyId={pid}")
conn.close()
```

## Troubleshooting

### Fast 403s (account-level)
- **Symptoms**: All accounts return 403 instantly (<0.1s), regardless of proxy
- **Diagnosis**: Accounts suspended (AWS-side), NOT proxy issue
- **Fix**: Register new accounts; no amount of proxy rotation helps

### 504 timeout / connection refused
- **Diagnosis**: Proxy unreachable — expired session, wrong URL, or IPRoyal balance depleted
- **Fix**: Verify proxy URL, recharge IPRoyal if needed, generate new session

### Proxy routing to wrong country
- **Symptoms**: IP geolocation shows SA (Saudi Arabia), DZ (Algeria) instead of US
- **Diagnosis**: Missing `_country-us` suffix in password
- **Fix**: Add `_country-us` parameter to password field

### Duplicate proxy URL in DB (UNIQUE constraint)
- **Symptoms**: SQLite `UNIQUE constraint failed: proxies.url` when updating
- **Diagnosis**: Both old and new rows tried to get same URL; `proxies.url` has UNIQUE constraint
- **Fix**: Deactivate old row, ensure only one row has the new URL with `is_active=1`

## Current Working Proxies (2026-05-15)

### ✅ IPRoyal US Residential (PRIMARY)
- **URL**: `http://4GJSsuSsb3vci2UA:4D9N9XyBb0weKTy8_country-us_city-hillside_session-9ZySUn49_lifetime-30m@geo.iproyal.com:12321`
- **出口 IP**: 99.103.40.6 (Hillside, IL, US)
- **ISP**: AT&T Enterprises (genuine residential)
- **Status**: ✅ Active — Kiro chat works, accounts validate correctly
- **Use**: All production traffic (9Router routing, account validation, registration)

### ○ Home Broadband (保留)
- **URL**: `http://100.64.247.23:7890`
- **出口 IP**: 120.244.143.67 (Shanghai, CN)
- **Status**: ○ Retired from primary use (IPRoyal now primary)
- **Use**: Emergency fallback only

## Best Practices

1. **Always use `_country-us_city-hillside_session-XXXX_lifetime-30m` format** — bare `_country-us` is unreliable
2. **Verify proxy IP + geolocation** before bulk operations
3. **Update all 7 locations** when switching proxies — check the checklist above
4. **Test with a single Kiro chat request** through 9Router to confirm end-to-end
5. **Use `proxyId` references** in 9Router connections (not per-connection URLs) — single update point
