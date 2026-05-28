---
name: batch-account-registration
description: >
  定时批量自动注册 Kiro + ChatGPT 账号。每 5-10 分钟随机间隔，
  通过 any-auto-register API 同时注册两个平台账号，注册后执行三步验证
  （Token 刷新 → 使用量查询 → AI 服务验证）。
  使用 IPRoyal 美国家庭宽带代理，cfworker 邮箱 + herosms 短信接码。
triggers:
  - 批量注册
  - 自动注册
  - batch register
  - scheduled registration
  - 定时注册
---

# Batch Account Registration — 定时批量自动注册

## 核心设计原则

- **少用 AI，多用脚本**：固定操作（API 调用、轮询、验证）全部由 Python 脚本执行。只有涉及语义理解、分析判断、产生操作指令的场景才用 AI
- **一致性优先**：脚本化操作消除 AI 随机性带来的偏差
- **自主执行**：整个过程不请示用户，完成批量后统一汇报

## 架构

```
cron (*/5分钟) ──→ scripts/auto_register_batch.py
                      ├─ 文件锁（全局 _lock_fd 保持 fd 不被 GC 释放）
                      ├─ 状态检查（上次<5min 则 50% 概率跳过，实现 5-10min 间隔）
                      ├─ Kiro (headed) + ChatGPT (protocol) 并行注册
                      ├─ 轮询至完成（15s 间隔，600s 超时）
                      └─ 三步验证新账号 → 写日志 + JSON 报告
```

关键实现细节：
- **锁机制**：使用模块级 `_lock_fd` 全局变量持有文件描述符，避免函数返回后被 GC 释放锁
- **间隔控制**：不再使用 `sleep`（会被 cron 超时截断），改用状态文件记录上次运行时间 + 概率跳过
- **时区**：`get_new_accounts` 使用 `datetime.now(timezone.utc)`，与数据库 UTC 时间戳对齐

## 脚本入口

```bash
python3 /root/.hermes/scripts/auto_register_batch.py
```

## 定时任务管理

```bash
hermes cron list
hermes cron pause 98718f87c50d
hermes cron resume 98718f87c50d
hermes cron run 98718f87c50d
```

## 注册参数

| 平台 | executor | 说明 |
|------|----------|------|
| Kiro | `headed` | 浏览器 OAuth 流程，需要 Xvfb + DISPLAY=:99 |
| ChatGPT | `headed` | **铁律：所有上游平台一律 headed**（2026-05-12 修正） |

## 注册铁律

**任何上游账号注册（Kiro、ChatGPT、及未来所有平台）一律用 headed 模式。**
headed 出技术问题时，只修不降级——严禁改成 protocol 或 headless。
headed 是唯一能稳定拿到 refreshToken 的方式。

## 三步验证

### Kiro
1. Token 刷新 (OIDC refreshToken → accessToken)
2. 使用量查询 (AWS Q API: `getUsageLimits`)
3. Chat API 验证 (`q.us-east-1.amazonaws.com/generateAssistantResponse` — **不是 CodeWhisperer**)

### ChatGPT
1. OAuth Token 刷新 (`auth.openai.com/oauth/token`)
2. 使用正确的 client_id: `app_EMoamEEZ73f0CkXaXp7hrann`, redirect_uri: `http://localhost:1455/auth/callback`
3. 验证 access_token 有效性 (`/backend-api/me` + `curl_cffi`)

⚠️ ChatGPT OAuth 陷阱：注册时用的 client_id 必须和 refresh 时一致。iOS client_id (`pdlLIXEutRQoZoYZSzfoKKmTSqYqKnBK`) 会返回 "Invalid client specified"。

## 已知问题与限制

### `token_refresh.py` / `payment.py` NameError 修复

如果批量注册/验证时出现 `NameError: name 'Account' is not defined`，需要在相关模块顶部添加 `from __future__ import annotations`。详见 `account-registration` 技能中「token_refresh.py 修复」章节。

### Kiro headed 模式铁律 ⚠️
**只能使用 `headed` 模式注册 Kiro。** 只有 headed（浏览器 OAuth）能获取 `refreshToken`。
protocol/headless 模式只能拿到 `accessToken`，无法用于后续验证和 9Router 同步。
**任何 headed 技术问题必须修复，严禁降级为 protocol/headless。**

### Desktop OIDC 回调端口修复（2026-05-12）✅
**问题**：`_desktop_idc_flow` 先注册 OIDC Client（硬编码 `redirectUris: ["http://127.0.0.1/oauth/callback"]`），
再启动回调服务器（随机端口），端口不匹配导致回调超时 → refreshToken 获取失败。

**修复**（`platforms/kiro/browser_register.py`）：
调整顺序 — 先启动 `_DesktopAuthCallbackServer` 拿到实际端口，
再用正确 URI (`http://127.0.0.1:{port}/oauth/callback`) 注册 OIDC Client。
修复后 headed 注册约 50% 产出完整 refreshToken（偶尔仍会超时，属正常波动）。

### ChatGPT 高频被拒
`registration_disallowed` — OpenAI 对 IP/邮箱风控。IPRoyal 代理 IP 可能被标记，
或 qhvip.cc 邮箱域名被 OpenAI 列入黑名单。部分批次可能成功，失败是正常波动。

### Cron 超时
`no_agent` 脚本模式默认 120s 超时。Kiro headed 模式注册需 60-180s。
移除 `sleep` 后脚本可在 120s 内完成；如果注册耗时过长会被截断，
但任务已在 any-auto-register 后台异步运行，下次 cron 会收到新任务。

## 配置参数

| 参数 | 值 | 说明 |
|------|-----|------|
| CRON | `*/5 * * * *` | 每 5 分钟触发 |
| SKIP_WINDOW | 300s | 上次执行 5 分钟内可能跳过 |
| SKIP_PROB | 0.5 | 跳过概率 |
| POLL_INTERVAL | 15s | 任务轮询间隔 |
| TASK_TIMEOUT | 600s | 单任务超时 |
| PROXY | IPRoyal US | `4GJSsuSsb3vci2UA:..._country-us_city-hillside_session-9ZySUn49_lifetime-30m@geo.iproyal.com:12321` (Hillside IL, AT&T) |

## 日志位置

- 主日志: `~/.hermes/logs/auto-register/register_YYYYMMDD.log`
- 批次报告: `~/.hermes/logs/auto-register/batch_YYYYMMDD_HHMMSS.json`
- 锁文件: `/tmp/auto_register_batch.lock`
- 状态文件: `/tmp/auto_register_batch_state.json`

## 依赖

| 组件 | 状态 | 详情 |
|------|------|------|
| any-auto-register | ✅ 8001 | systemd 服务 |
| Xvfb | ✅ :99 | headed 模式必须 |
| IPRoyal 代理 | ✅ | 代理池统一管理 |
| cfworker 邮箱 | ✅ | qhvip.cc 域 |
| herosms | ✅ | 短信接码 |
| curl_cffi | ✅ | API 验证用 |

## 相关技能

- `account-registration` — any-auto-register 注册流程详解、**Codex token 重新授权**（含 3 路径降级、`from __future__ import annotations` 修复、Auth0 refresh token rotation 说明）
- `kiro-account-validation` — Kiro 三步验证方法
- `platform-to-9router-sync` — 新账号同步到 9Router
- `references/desktop-oidc-callback-fix.md` — Desktop OIDC 端口修复详情
- `account-registration` 内 `references/codex-token-reauthorization.md` — **2026-05-23 批量重新授权实战记录**（token_refresh.py 修复、Camoufox OAuth 流程、JWT 解码、OTP callback 陷阱）
