# import-tool Development Pitfalls

Bugs encountered, root causes, and fixes applied during development. Read before modifying server.py or import_accounts.py.

---

## Pitfall 1: JSON body mode crashes on file.filename

**Symptom**: `UnboundLocalError: cannot access local variable 'file'` when POSTing JSON body.
**Cause**: Added `elif request.is_json:` branch in upload(), but downstream code referenced `file.filename` — only defined in `if 'file' in request.files:`.
**Fix**: `f"收到{'文件: ' + file.filename if 'file' in request.files else 'JSON 数据'}"`

---

## Pitfall 2: time.sleep() NameError in import script

**Symptom**: `NameError: name 'time' is not defined` in poll_status().
**Cause**: `import time as time_module` scoped to main() but poll_status() is top-level.
**Fix**: Move `import time as time_module` to module top. Replace all bare `time.sleep()`.

---

## Pitfall 3: Validation timeout ≠ account is dead

**Symptom**: 6 accounts "验证错误: Read timed out". User thought they weren't imported.
**Reality**: Import (Phase A) and validation (Phase B) are independent. Timeout = proxy slow, not account dead.
**Fix**: Show `current_account` in progress bar. Preserve testStatus on UPDATE. Communicate clearly.

---

## Pitfall 4: Progress bar appears frozen

**Symptom**: Same step shown for multiple 5s polling cycles.
**Cause**: Validation HTTP calls took 25s. Polling at 5s → 5 intervals with no progress update.
**Fix**: Timeout 25→15s + add `current_account` field: `[====] 5/24 通过 2 ... Account 11 (abigail@...)`

---

## Pitfall 5: UPDATE overwrites 9Router health check data

**Symptom**: Re-import resets testStatus and backoffLevel.
**Cause**: import_accounts() builds fresh auth_data dict, overwrites entire data JSON column on UPDATE.
**Fix**: On UPDATE, merge only token fields (accessToken, refreshToken, expiresAt). Preserve testStatus, backoffLevel, lastUsedAt, etc.

---

## Pitfall 6: Kiro validation wastes LLM tokens

**Symptom**: Every account made a real v1/chat/completions call through 9Router.
**Fix**: Added `validate_kiro_zerocost()`:
- Step 1: OIDC token refresh (no LLM)
- Step 2: GET /getUsageLimits (quota check, no LLM)
- Only Codex still uses LLM validation (no equivalent zero-cost endpoint exists).

---

## Pitfall 7: Validation thread lacks token data

**Symptom**: Kiro validation needed clientId/clientSecret but all_imported dict didn't include them.
**Fix**: Added accessToken, refreshToken, clientId, clientSecret to all_imported entries.

---

## Architecture: Two-phase design

```
Phase A — import_accounts()     [synchronous]
  Read → validate → write SQLite → return stats

Phase B — validate_accounts_async()  [background thread]
  Test each → report via /api/status
```

Phase B failures do NOT roll back Phase A. Accounts stay in DB.
