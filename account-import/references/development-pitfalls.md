# Development Pitfalls — account-import skill

Lessons learned building and iterating on this skill.

## Validation: Real LLM Calls Only

**Do NOT use zero-cost validation** (token refresh + quota query). The user explicitly rejected this approach — token validity ≠ chat API availability. Always validate through 9Router with real LLM calls:

```
Codex: cx/gpt-5.5  ("1+1", max_tokens=3, timeout=15)
Kiro:  kr/claude-haiku-4.5  ("1+1", max_tokens=3, timeout=15)
```

Cost is ~50 tokens per validation, acceptable for the certainty gained.

## Timeout Tuning

- 25s was too long — failed accounts blocked the progress bar for full 25s
- 15s is the sweet spot — valid accounts respond in 3-5s through IPRoyal proxy
- Some accounts legitimately need more time (proxy route selection). These show as "Read timed out" but are still `active=1` in DB and usable with 9Router's 60s default timeout.

## Progress Bar: Show Current Account

Without `current_account` in the status response, the progress bar appeared stuck when a slow account was being tested. Always include:

```python
current_status["current_account"] = f"{acc['name']} ({acc['email']})"
```

The polling script then shows: `[====     ] 5/24 通过 3 ... Account 11 (user@domain.com)`

## Update vs Overwrite

When updating existing connections, only refresh tokens/expiresAt — preserve 9Router's own `testStatus` and `backoffLevel`:

```python
old_data = json.loads(existing_row[0])
old_data['accessToken'] = new_token
old_data['refreshToken'] = new_rt
old_data['expiresAt'] = new_expiry
# Keep: old_data['testStatus'], old_data['backoffLevel']
```

## Import-tool Endpoint

The import-tool (`/root/import-tool/server.py`) runs on port 8500. It supports:
- Multipart file upload: `POST /api/upload` with `file=` parameter
- Raw JSON body: same endpoint, `Content-Type: application/json`

When adding JSON body support, fix all references to `file.filename` in logs — use conditional:
```python
add_log(f"收到{'文件: ' + file.filename if 'file' in request.files else 'JSON 数据'}")
```

## Publishing

```bash
hermes skills publish /path/to/skill --to github --repo chenkaihao/hermes-skills
hermes skills install chenkaihao/hermes-skills/account-import --category automation --force
```

Security scan false positives (safe to ignore):
- `sys.platform` check → flagged as "exfiltration" (it's just cross-platform color support)
- `b"\xef\xbb\xbf"` BOM check → flagged as "obfuscation" (it's UTF-8 BOM handling for Windows Excel)

## 9Router Database

Authoritative DB: `/root/src/9router-data/db/data.sqlite` (SQLite), NOT `db.json`. The db.json is the pre-migration format.

## Output Buffering (Background Processes)

When running `monitor_survival.py` via the background process tool (`terminal(background=true)`), Python's stdout is fully buffered and the process tracker shows zero output until completion. Two fixes are required:

1. **Always use `python3 -u`** (unbuffered) when running from cron or background
2. **Every `print()` needs `flush=True`** — especially in long-running loops

```bash
python3 -u /path/to/monitor_survival.py 2>&1
```

For foreground testing, `exec(open('script.py').read())` works better than subprocess.

## `import time` Shadowing

When importing `time as time_module` at module level, don't re-import `time` inside `main()`. The `time_module.sleep(2)` call in `main()` will break if bare `time` is re-imported locally. Keep a single import at the top:

```python
import time as time_module  # once, at module level
```

## Survival Monitor First-Run

The first survival monitor run seeds `account_lifespan` from scratch — all accounts have `first_seen = now`, so median lifespan is 0.0 days. True lifespan data accumulates over multiple 6-hour runs.

With 10s timeout and 3 concurrency, ~100 accounts complete in ~5-7 minutes. Most first-run "deaths" are timeouts, not real bans — accounts become stable after 2-3 observation cycles.
