# Survival Monitor — Pitfalls & Findings

*Last updated: 2026-05-21*

## load_lifespan() missing provider/domain columns

**Symptom**: HTML report shows empty platform columns ("二、平台对比" table blank), all domains show "unknown" in domain ranking, "长寿榜" has no platform info.

**Root cause**: `load_lifespan()` at line 39 originally only SELECTed `email, status, first_seen, last_alive, died_at, death_reason, check_count` — omitting `provider` and `domain`. Since these fields existed in the DB but weren't loaded, `v.get("provider", "")` returned empty and `v.get("domain", "unknown")` returned "unknown" for every entry.

**Fix applied (2026-05-21)**:
```python
# BEFORE (broken):
rows = conn.execute("SELECT email, status, first_seen, last_alive, died_at, death_reason, check_count FROM account_lifespan").fetchall()
return {r[0]: {"status": r[1], "first_seen": r[2], "last_alive": r[3], "died_at": r[4], "death_reason": r[5], "check_count": r[6]} for r in rows}

# AFTER (fixed):
rows = conn.execute("SELECT email, provider, domain, status, first_seen, last_alive, died_at, death_reason, check_count FROM account_lifespan").fetchall()
return {r[0]: {"provider": r[1], "domain": r[2], "status": r[3], "first_seen": r[4], "last_alive": r[5], "died_at": r[6], "death_reason": r[7], "check_count": r[8]} for r in rows}
```

**Detection**: Run `--report-only` and check HTML tables — if platform columns are empty, this bug is present.

## Cron: no_agent silently kills long scripts

**Symptom**: Cron shows `last_status: error`, job triggers every 6h but DB never updates (check_count stays at 1), HTML never refreshes.

**Root cause**: `no_agent=true` cron mode has a **120s hard timeout**. The survival monitor processes ~99 accounts × 25s timeout ÷ 3 concurrency = ~8-10 minutes. All 4 scheduled runs failed with:
```
Script timed out after 120s: /root/.hermes/scripts/monitor_survival.py
```

**Evidence**: `/root/.hermes/cron/output/fb4cfeacc72a/2026-05-21_12-02-05.md`:
```
**Mode:** no_agent (script)
**Status:** script failed
Script timed out after 120s
```

**Fix**: Switched to agent mode (`no_agent=false`) with terminal toolset. Terminal timeout is 600s — sufficient.

**Verification**: After switching to agent mode, script completed successfully. DB check_count went from 1 → 2.

```bash
# Check cron output for silent timeouts
ls /root/.hermes/cron/output/<job_id>/
tail /root/.hermes/cron/output/<job_id>/<latest>.md
```

## Codex (OpenAI) rotating refresh tokens are one-time-use

**Finding**: OpenAI Codex uses **rotating (one-time-use) refresh tokens**. Each refresh token can only be used once — a successful refresh returns a NEW refresh token that must be saved for next use.

**Error on re-use**:
```json
{
  "error": {
    "message": "Your refresh token has already been used to generate a new access token. Please try signing in again.",
    "type": "invalid_request_error",
    "code": "refresh_token_reused"
  }
}
```

**Implications for survival monitoring**:

- When 9router shows `testStatus: unavailable` with `lastError: "401: Provided authentication token is expired"`, the refresh token is already consumed
- Manual token refresh is **impossible** — all 12 tested RTs returned `refresh_token_reused`
- Recovery requires **full OAuth re-authentication** (headed browser, email verification, etc.)
- 9router's auto-refresh may consume the RT without successfully persisting the new AT/RT pair

**Shared RT anti-pattern**: 7 accounts (`brandonparker2024`, `vincentr33`, `amiller83`, `cherylsun90`, `dwalker79`, `andersonanthony`, `dylana2024`) share the same refresh token `rt_W11R4VzQ5y4wOKdkTo1mZxpGbmJ...`. One refresh consumed it for all 7 — a single failure kills the entire cluster.

**OAuth endpoint for manual testing**:
```
POST https://auth.openai.com/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token
refresh_token=<rt>
client_id=app_EMoamEEZ73f0CkXaXp7hrann
scope=openid profile email offline_access
```

## Death reason classification with 9Router health fallback

When `monitor_survival.py` calls 9Router's chat API and gets empty body or timeout, the real cause may be:
- **Proxy slowness** → true timeout
- **Upstream 403/401** → 9Router returns empty/error instead of proxying the 403

The fallback (`get_9router_health()`) queries 9Router's own health data:

```sql
SELECT json_extract(data, '$.testStatus'), json_extract(data, '$.lastError')
FROM providerConnections WHERE email=?
```

Classification rules:
| 9Router testStatus | lastError pattern | → death_reason |
|---|---|---|
| `unavailable` | contains `403`, `suspended`, `banned` | **封号** |
| `unavailable` | contains `401`, `expired`, `invalid` | **token失效** |
| `unavailable` | contains `429`, `rate` | **限流** |
| `untested` / no error | — | **超时** (unknown) |

**Before this fix**: All 26 Kiro accounts showed "超时" or "Expecting value", masking the real cause (AWS 403 suspended). After fix: 17 correctly classified as "封号".

## Kiro mass die-off confirmed

- 26 Kiro accounts, all `testStatus: unavailable` in 9Router
- All show AWS 403: "Your User ID (...) temporarily suspended"
- Previously (2026-05-12): 9/21 alive via direct three-step verification
- Now (2026-05-21): 0/26 alive — mass ban event between May 12-20

## Round-over-round tracking

| Round | Alive | Dead | Codex alive | Notable |
|-------|-------|------|-------------|---------|
| 1 (10s timeout, discarded) | 39 | 60 | — | Timeout too aggressive |
| 1 (25s, clean) | 61 | 38 | 61/73 (83.6%) | Kiro 0/26 |
| 2 | 46 | 53 | 46/73 (63.0%) | −15 Codex token失效 |

Round 2 deaths: 23 "token失效" (all Codex), 17 "封号" (Kiro), 6 "超时", 6 "Expecting value", 1 "限流".
