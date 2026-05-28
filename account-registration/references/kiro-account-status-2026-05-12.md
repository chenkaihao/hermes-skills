# Kiro Account Status Snapshot — 2026-05-12

## Latest Run (44 accounts with Chat API)

**Test time**: 2026-05-12 20:21 CST (12:21 UTC)  
**Proxy**: IPRoyal 美国家庭宽带 (`geo.iproyal.com` + `_country-us`, export IP: 154.6.51.72 Seattle)  
**Method**: Three-step validation with **Chat API** for step 3 (`generateAssistantResponse`)

### Summary

| Metric | Value |
|--------|-------|
| Total | **44** (up from 21 — auto-registration running) |
| ✅ Valid | 20 (45.5%) |
| ❌ Invalid | 24 (54.5%) |
| Invalid: AWS 403 suspended | 23 (95.8%) |
| Invalid: proxy 504 transient | 1 (4.2%) |

### Valid Accounts (20)

All new accounts registered by the batch auto-registration system. All use `@qhvip.cc` domain.

| ID | Email |
|----|-------|
| 44 | wangamanda82@qhvip.cc |
| 45 | nicholasg92@qhvip.cc |
| 46 | gomezc35@qhvip.cc |
| 47 | ericprice48@qhvip.cc |
| 48 | thomase2020@qhvip.cc |
| 50 | elizabethwilliams@qhvip.cc |
| 54 | harrise2022@qhvip.cc |
| 55 | floress2021@qhvip.cc |
| 57 | christopherp94@qhvip.cc |
| 59 | dianeroberts@qhvip.cc |
| 60 | douglass@qhvip.cc |
| 61 | masonjimenez81@qhvip.cc |
| 63 | markhe2022@qhvip.cc |
| 65 | lucasj43@qhvip.cc |
| 67 | jasonclark@qhvip.cc |
| 68 | lauralong50@qhvip.cc |
| 71 | joesimmons91@qhvip.cc |
| 75 | aidenthompson93@qhvip.cc |
| 76 | josephkim81@qhvip.cc |
| 79 | wrightv81@qhvip.cc |

All passed Chat API test with `generateAssistantResponse` — confirmed operational.

### Invalid Accounts (24)

**23 accounts**: AWS 403 `temporarily is suspended` — "We've locked your account as a security precaution."

| ID | Email | User ID (truncated) |
|----|-------|---------------------|
| 9 | kaplan72f2a0@tr.26ai.org | f40884f8-... |
| 10 | joshuachen79@qhvip.cc | (proxy 504, may be valid) |
| 11 | joshuareyes@qhvip.cc | 741844a8-... |
| 12 | annabutler89@qhvip.cc | e4c864b8-... |
| 15 | mbailey2022@qhvip.cc | f45834e8-... |
| 22 | calebzhang88@qhvip.cc | 74780478-... |
| 23 | elizabethsmith@qhvip.cc | 44980478-... |
| 24 | susanr55@qhvip.cc | 34088438-... |
| 25 | her68@qhvip.cc | 7448d4f8-... |
| 26 | shu@qhvip.cc | 449884c8-... |
| 27 | stewartnicholas90@qhvip.cc | 44080438-... |
| 28 | jonesm@qhvip.cc | 0438d4d8-... |
| 49 | clarkmartha65@qhvip.cc | 94a8f468-... |
| 52 | royperry@qhvip.cc | 742824f8-... |
| 53 | jkim40@qhvip.cc | b458c478-... |
| 56 | chloew89@qhvip.cc | b4887408-... |
| 58 | sharona2023@qhvip.cc | 54e8a498-... |
| 62 | gjenkins90@qhvip.cc | b488a478-... |
| 64 | loganrobinson2024@qhvip.cc | 24a87438-... |
| 66 | ralphgreen2024@qhvip.cc | 64b8d4f8-... |
| 69 | samanthaking85@qhvip.cc | f4a844f8-... |
| 73 | cynthial@qhvip.cc | b418c488-... |
| 74 | emilys2025@qhvip.cc | 04b81488-... |
| 77 | pamelacox@qhvip.cc | 94f814e8-... |

**Key observation**: The original 9 valid accounts from the earlier run (IDs 7, 8, 13, 14, 16, 17, 18, 19, 20) are NO LONGER in the database — they've been replaced by the batch auto-registration system. Old accounts with legacy tokens were purged.

## 9Router Connection State (2026-05-12 20:15)

- **Kiro AI Provider**: 24 Connected (Web UI)
- **Proxy Pool**: IPRoyal US ✅ active, 24 bound, health check passing
- **better-sqlite3**: ✅ native module loaded (was broken after v0.4.31 upgrade, fixed)
- **toWellFormed bug**: ✅ fixed via `NODE_OPTIONS=--require preload.js` in systemd

### 9Router v0.4.31 Upgrade Notes

The upgrade from v0.4.20 introduced three issues, all resolved:
1. **better-sqlite3 NODE_MODULE_VERSION mismatch** — build used Node v24 (127), systemd used Node v18 (109). Fixed by pointing systemd to nvm Node v22 and running `npm rebuild better-sqlite3`.
2. **toWellFormed polyfill** — webpack strips `File` global, undici v6+ needs it for proxy tests. Fixed with `preload.js` loaded via `NODE_OPTIONS` env var (NOT `--require` in ExecStart — systemd doesn't shell-parse quotes).
3. **systemd --require quoting trap** — `--require "/path"` passes the literal quotes to Node. Use `Environment="NODE_OPTIONS=--require /path"` instead.
See `references/9router-systemd-pitfalls.md` for full details.

## Historical Context

- **2026-05-12 01:43**: Initial run — 21 accounts, 9 valid (42.9%), home broadband proxy
- **2026-05-12 01:54**: Re-test with IPRoyal US — same result, confirmed proxy-independent
- **2026-05-12 20:21**: Latest run — 44 accounts, 20 valid (45.5%), chat API method, IPRoyal US proxy
- Growth from 21→44 accounts via `batch-account-registration` skill (headed mode, 5-10min intervals)
