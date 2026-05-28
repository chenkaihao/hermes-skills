---
name: account-import
description: "Import third-party accounts into 9Router. When someone provides account files (JSON/CSV/text), follow this skill to validate, convert, and push them to our system. Only use AI for format understanding and provider communication — delegate all mechanical work to the import script."
category: automation
---

# Account Import — 第三方账号导入

## Trigger

Load this skill when:
- Someone sends account data (file attachment, pasted JSON/CSV, text dump)
- Someone says "帮我导入这些账号" / "here are some accounts" / "导入账号" / "import account to 9Router"
- Someone asks how to send accounts to us
- You see a file named like `*export*.json`, `*accounts*.csv`, `*codex*.json`
- You need to **directly insert** an account from any-auto-register into 9Router SQLite (server-side import)

## Direct Server-Side Import (no web API)

When ON the server and importing from any-auto-register → 9Router directly, the web import API may be unnecessary overhead. Instead:

1. Read credentials from any-auto-register's `account_credentials` table
2. Build a `providerConnections` entry matching existing Codex entries' format (see `account-registration` references for schema)
3. `INSERT` into `/root/src/9router-data/db/data.sqlite` (check email first to avoid duplicates)
4. Sync the entry to `db.json` backup
5. `systemctl restart 9router`
6. Run health check (see `account-registration` skill's `references/codex-health-check.md`)

## Core Principle

```
Script does mechanical work    →    AI does judgment work
────────────────────────────        ───────────────────────
Parse JSON/CSV/BOM                  Understand what the data IS
Validate tokens/emails/dates        Decide which platform it belongs to
Detect duplicates                   Explain errors to provider
HTTP push to server                 Suggest fixes for bad data
Show preview/results                Communicate in natural language
```

**Never** manually parse the file yourself. **Always** delegate to `scripts/import_accounts.py`.

## Procedure

### Phase 1: Understand what they have

1. Ask the provider: "你的账号数据是什么格式？文件还是文本？"
2. If they have a file, note its extension (`.json`, `.csv`, `.txt`).
3. If they pasted text, save it to a temp file first.
4. **Do NOT read the file yourself.** The script handles all formats.

### Phase 2: First pass with the script

Run the script in dry-run mode to see what it detects:

```bash
python scripts/import_accounts.py --input <file> --dry-run
```

The script will output:
- Detected platform(s)
- Account count
- Validation errors (if any)
- Duplicate warnings

### Phase 3: Interpret results — AI judgment required

Based on the script output, handle these cases:

#### Case A: Clean — all accounts pass, platform detected correctly
→ Proceed to Phase 4 (push).

#### Case B: Platform detected wrong
Example: script says `kiro` but the accounts are actually `codex`.
→ Re-run with explicit `--platform`:
```bash
python scripts/import_accounts.py --input <file> --platform codex --dry-run
```
How to tell: Kiro tokens start with `rt.1.AAA`. Codex tokens start with `rt_` or are JWT (`eyJ...`).

#### Case C: Validation errors — "Token 格式异常"
Example: `refreshToken 格式异常（Codex token 应以 rt_ 或 eyJ 开头）`
→ Common causes:
- **Kiro token mixed in Codex batch**: This is fine. The token format is valid for Kiro but was placed in a Codex file. It will still import correctly. Tell the provider "这个 token 是 Kiro 格式，但不影响导入，系统会自动处理。"
- **Truncated token**: Token was cut off during copy-paste. Ask provider to re-export.
- **Wrong platform**: User specified wrong `--platform`. Re-run with correct one.

#### Case D: "无法识别的格式"
Script can't parse the data.
→ **This needs AI.** Read the first few lines of the file yourself to understand its structure, then:
- If it's an Excel file (`.xlsx`): ask provider to export as CSV
- If it's wrapped in extra JSON layers: strip the wrapper manually with a small Python snippet
- If it's a completely custom format: map the fields to our schema (see Phase 2b below)
- If it's plain text with account list: extract structured data

#### Case E: Script errors on their machine
Provider reports `python not found` or `ImportError`.
→ Guide them:
- Windows: `python --version`. If not found, download from python.org, check "Add to PATH"
- Mac/Linux: `python3 --version`. If not found, `brew install python3` or `apt install python3`
- Script download: `curl -O https://tokenfree.cc/report/import_accounts.py` (or they can copy it from our skills directory)

### Phase 2b: Convert custom format (AI-only step)

When the data is not in a format the script understands, create a converter. Keep it minimal:

```python
import json
raw = <read provider's data>
converted = {"codex": []}  # or "kiro"
for item in raw:
    converted["codex"].append({
        "email": item.get("<their email field>"),
        "refreshToken": item.get("<their token field>"),
        "accessToken": item.get("<their access field>", ""),
        "expiresAt": item.get("<their expiry field>", ""),
        "name": item.get("<their name field>", ""),
    })
with open("converted.json", "w") as f:
    json.dump(converted, f)
```

Then run the script on the converted file.

### Phase 4: Provider runs the push

If the provider is running the script themselves:
```
python import_accounts.py --input accounts.json --push
```

If YOU are running it on our server:
```bash
python /root/.hermes/skills/automation/account-import/scripts/import_accounts.py \
    --input <file> --push -y
```

The script will:
1. Show a preview
2. Ask for confirmation (unless `-y`)
3. POST to `https://tokenfree.cc/import/api/upload`
4. Poll for validation results with live `current_account` display
5. Show final report

> **Note**: When re-importing existing accounts (same email), the server only updates tokens — it preserves 9Router's own health check state (testStatus/backoffLevel). Import and validation are independent steps.

### Phase 5: Handle push errors

> ⚠️ **Import writes to DB. Validation is a health check. They are independent.**
> A "验证失败" does NOT mean the account wasn't imported. All accounts are in the DB.
> Validation timeouts usually mean proxy slowness, not dead accounts.

| Error | Cause | Action |
|-------|-------|--------|
| `网络错误` | Provider can't reach tokenfree.cc | Check internet. `curl https://tokenfree.cc/report/` |
| `HTTP 500` | Server-side issue | `journalctl -u import-tool --no-pager -n 30` |
| `HTTP 400` | Content-Type wrong | Script sends `application/json` automatically |
| "验证超时" / "Read timed out" | Proxy slow for some accounts | **Accounts ARE imported.** Tell provider "已导入，部分账号代理较慢暂未通过快速检查，系统会在实际请求时自动重试。" |
| `导入完成: +0新/0更` | All duplicates | Tokens refreshed if different. Report success. |

### Phase 6: Report back

Always summarize to the provider:
```
✅ 导入完成
   新增: X 个
   更新: Y 个
   验证通过: Z/W
```

If any accounts failed validation, list them with reasons.

## Script Reference

Location: `scripts/import_accounts.py` (516 lines, zero dependencies)

### Full flags

```
--input, -i      Input file (JSON/CSV)
--platform, -p   Force platform: kiro, codex, chatgpt, claude
--push           Push to server (omit for local preview only)
--export, -o     Export validated JSON to file
--dry-run        Preview without importing
--endpoint       Custom API endpoint (default: tokenfree.cc)
--api-key        Auth key (if server requires it)
--yes, -y        Skip confirmation prompt
```

### What the script auto-detects

- **Platform** (3-layer): `provider` field → token pattern (`rt.1.A`=Kiro, `rt_`=Codex, `eyJ`=JWT) → email domain
- **Field mapping** (30+ aliases): `token`/`key`/`access_token` → `accessToken`, `mail`/`username`/`login` → `email`
- **Encoding**: UTF-8 BOM (Windows Excel), CRLF line endings
- **Format**: 9Router export (`providerConnections`), grouped (`{"codex":[...]}`), flat list (`[{...}]`), CSV

### What the script does NOT do

- Read Excel (`.xlsx`) — ask provider to export as CSV
- Guess field meanings from completely custom names — that's AI's job
- Retry on transient network errors — re-run manually
- Merge accounts from multiple files — run once per file

## Server API

The script pushes to our import-tool service:

```
POST https://tokenfree.cc/import/api/upload
Content-Type: application/json

{"codex": [...], "kiro": [...]}
```

Response:
```json
{"success": true, "stats": {"codex": {"new": 3, "updated": 1}}, "total": 4, "phase": "validating"}
```

The import-tool:
1. Writes to `/root/src/9router-data/db/data.sqlite`
2. Restarts 9Router
3. Validates each account via real LLM calls through 9Router (Kiro: kr/claude-haiku-4.5, Codex: cx/gpt-5.5, max_tokens=3, timeout=15s)
4. On UPDATE, preserves 9Router's testStatus/backoffLevel
5. Returns results at `GET /import/api/status`

> 🔥 **Git 追踪**：9Router 数据目录 `/root/src/9router-data` 应已初始化为 Git 仓库（含 `.gitignore` 排除 WAL/SHM/日志/备份）。每次导入后必须 `git diff --stat` 确认只改动了预期条目、`git commit` 记录变更。详见 `account-registration` 技能的 `references/git-tracking-9router-data.md`。
>
> **SQLite WAL 陷阱**：导入后 `git diff` 可能只显示 `db.json` 变更而 `data.sqlite` hash 不变——数据已写入，只是 WAL 尚未 checkpoint。通过 SQL 查询确认而非依赖 git diff 判定。

## Publishing

```bash
hermes skills Publish to GitHub to sync updated SKILL.md + new pitfalls reference. /path/to/skill --to github --repo chenkaihao/hermes-skills
hermes skills install chenkaihao/hermes-skills/account-import --category automation --force
```

`--force` needed for false-positive security scan (cross-platform `sys.platform` check + UTF-8 BOM handler).

See `references/development-pitfalls.md` for lessons learned building this skill.
See `references/survival-monitor-pitfalls.md` for cron timeout, token refresh, and death classification pitfalls.

## Provider-facing instructions

When a provider needs step-by-step guidance, send them this (translated to their language):

---

**下载脚本**: https://tokenfree.cc/report/import_accounts.py

**准备数据** — 推荐 9Router 导出的 JSON 文件，或者用这个格式：
```json
{"codex": [{"email": "xxx@xxx.com", "refreshToken": "rt_xxx", "accessToken": "eyJ...", "expiresAt": "2026-01-01T00:00:00Z"}]}
```

**运行**:
```bash
python import_accounts.py --input 你的文件.json --push
```

三步：下载 → 准备文件 → 运行。出错了把输出发给我。


## Survival Monitoring — 账号存活观测

This skill includes an automated survival monitor (`scripts/monitor_survival.py`) running every 6 hours via cron (zero LLM cost, `no_agent=true`).

### How it works

1. Reads all active accounts from 9Router DB (`providerConnections` table)
2. Validates each via real LLM call through 9Router (Codex: `cx/gpt-5.5`, Kiro: `kr/claude-haiku-4.5`, max_tokens=3)
3. **On API failure, falls back to 9Router health data** — queries `providerConnections.testStatus` + `lastError` for accurate ban classification (prevents "超时" false positives when the real cause is 403 suspended)
4. Records alive/dead state with timestamps in `account_lifespan` table
5. Generates HTML report at `/var/www/html/report/survival.html`

### Key parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| `TIMEOUT` | **25s** | 10s too aggressive; Kiro OIDC+Chat end-to-end needs 15-20s |
| `CONCURRENCY` | 3 | Thread pool for parallel validation |
| `API` | `http://localhost:3000/v1/chat/completions` | Via New API routing (Docker). Port 9000 is Next.js UI — `/v1/` returns 404 there. |

### Report modules

- Total / alive / dead counts + 7-day death rate + median lifespan
- Platform comparison (Kiro vs Codex) with bar charts
- Domain anti-ban ranking
- Survival curve (Kaplan-Meier style)
- Recent deaths with color-coded reasons (封号=red, 超时=yellow)
- Longest surviving accounts TOP10

### Manual run

```bash
# Full check (validates all accounts → updates DB → generates HTML)
python /root/.hermes/skills/automation/account-import/scripts/monitor_survival.py

# Report-only mode (regenerate HTML from existing DB, no API calls)
python /root/.hermes/skills/automation/account-import/scripts/monitor_survival.py --report-only
```

Report: https://tokenfree.cc/report/survival.html

### 9Router health fallback (critical)

When chat API returns empty body or times out, the script queries 9Router's provider health:

```sql
SELECT json_extract(data, '$.testStatus'), json_extract(data, '$.lastError')
FROM providerConnections WHERE email=?
```

If `testStatus == "unavailable"` with 403/suspended in `lastError`, classified as **封号** — not 超时. This prevents proxy-delay false positives from masquerading as real bans.

### Cron

⚠️ **CRITICAL: Agent mode required (not `no_agent`)**

`no_agent=true` cron mode has a **120s hard timeout**. The survival monitor takes 8-10 minutes (99 accounts × 25s ÷ 3 concurrency). All `no_agent` runs silently fail with `Script timed out after 120s` — no error visible unless checking `/root/.hermes/cron/output/<job_id>/` files.

**Correct setup**:
```json
{
  "no_agent": false,      // ← must be false for long-running scripts
  "enabled_toolsets": ["terminal"],
  "prompt": "运行存活观测脚本：python3 -u /root/.hermes/skills/automation/account-import/scripts/monitor_survival.py。只需运行脚本，脚本会自己生成 HTML 报表。"
}
```

Terminal timeout in agent mode is 600s — sufficient. Cost: ~1 LLM turn per run (negligible at ~500 tokens).

Script must exist in `~/.hermes/scripts/` (cron requires flat directory, not skill path). Sync when updating:

```bash
cp /root/.hermes/skills/automation/account-import/scripts/monitor_survival.py /root/.hermes/scripts/
```

### Pitfalls discovered

- **10s timeout → false die-off**: First runs showed 60 dead/39 alive. 25s doubled alive to 61.
- **`load_lifespan()` missing columns**: Originally omitted `provider, domain` from SELECT — HTML showed empty platforms and "unknown" domains. Fixed by including both in the query.
- **Kiro "超时" may be actual bans**: 9Router returns empty body for connections with 403 upstream. Without health fallback, these show as "Expecting value" instead of "封号".
- **`no_agent` cron silently kills long scripts**: 120s hard timeout for script-only mode. All 4 scheduled runs failed silently. Switched to agent mode (600s terminal timeout). See `references/survival-monitor-pitfalls.md`.
- **Codex refresh tokens are one-time-use**: OpenAI uses rotating RTs. Once consumed (by 9Router auto-refresh or any other process), permanent `refresh_token_reused` error. Recovery requires full OAuth re-authentication — token refresh impossible. See `references/survival-monitor-pitfalls.md`.
