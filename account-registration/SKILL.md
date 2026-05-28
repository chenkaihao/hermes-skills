---
name: account-registration
description: >
  自动账号全生命周期管理：多平台账号批量注册（headed/headless 浏览器模式、
  邮箱/手机验证、OAuth 流程、代理与接码平台）、注册后 token 验证与刷新、
  以及同步到 9Router（含 v0.4.31+ SQLite schema）。适用于需要注册、
  验证和管理大量 AI 平台账号（ChatGPT、Kiro、Windsurf 等）的场景。
triggers:
  - register account
  - auto register
  - batch registration
  - sign up automation
  - 注册账号
  - 自动注册
  - reauthorize codex
  - refresh expired tokens
  - token expired
  - codex_refresh
  - 重新授权
  - token 过期
---

# Account Registration — 自动账号注册工作流

## 约束与偏好

> 本技能编码用户对注册任务的核心约束，任何执行此类任务时必须遵守。

### 浏览器模式选择
- ** headed 优先**：默认使用 `headed` 模式（有头浏览器），除非用户明确授权 `headless`
- **禁止静默降级**：遇到 headed 失败时不得私自切换到 headless，必须先解决 headed 环境问题
- **服务器 headed 依赖**： headed 模式在服务器上依赖 `xvfb` 提供虚拟显示

### 网络与代理
- **✅ 代理 fallback 已正常工作**（2026-05-26 验证）：`application/tasks.py` 第 759 行 `resolved_proxy = proxy or proxy_pool.get_next()` — 前端传 `null` 时自动从 proxy_pool 选取默认代理。
  - 任务日志确认：`使用代理: http://4GJSsuSsb3vci2UA:***@geo.iproyal.com:12321`，代理测速正常后开始注册。
  - 如遇注册时未使用代理，先查日志确认 `使用代理` 行有无输出，可能原因：proxy_pool 返回 None（代理 `is_active=0`）、或代理 URL 解析异常。
- **代理状态检查**：注册前必须查询 `proxies` 表，确认目标代理 `is_active=1`
- **IPRoyal US 代理**：`http://user:pass_country-us@geo.iproyal.com:12321`（密码含 `_country-us` 后缀指定美国节点，出口 IP `154.6.51.72` Seattle）。切换国家：改后缀如 `_country-gb`（英国）、`_country-ca`（加拿大）。

### 执行风格
- **自主执行**：用户明确要求"不要问我，不要经过我同意，所有的事情都做完后，向我汇报结果"。这意味着：
  - 注册前检查环境、禁用代理等前置步骤自动执行，不请示
  - 遇到可自动恢复的问题（如 OAuth 验证失败重试）直接处理
  - 整个批次注册完成后统一汇报，不中途询问
  - 仅当遇到无法自行解决的阻塞性问题时才暂停并告知用户
  - **结果驱动**：用户说"拿不到结果不要停"时，意味着最终交付物是可用状态（如 New API 操练场能成功调通），不是中间产出（如"token 已刷新"）。遇到阻塞时追到根因，不要停留在表面修复。

### Kiro 注册铁律 ⚠️
- **只能用 `headed` 模式**：只有 headed（浏览器 OAuth）能产出 `refreshToken` + `clientId` + `clientSecret`。protocol/headless 只能拿到 `accessToken`，无法用于后续验证和 9Router 同步。
- **严禁降级**：headed 出现 Xvfb、浏览器崩溃、回调超时等问题时，必须解决根因，严禁改为 protocol 或 headless。
- **Desktop OIDC 端口修复**（已在 `platforms/kiro/browser_register.py` 修复）：先启动 `_DesktopAuthCallbackServer` 获取实际端口，再用正确 URI 注册 OIDC Client。旧代码先注册客户端（硬编码无端口 URI）再启服务器，导致回调超时。

---

## 前置环境检查

### 1. Xvfb 虚拟显示（headed 模式必需）

```bash
# 检查 Xvfb 是否安装
which Xvfb || apt-get update && apt-get install -y xvfb

# 检查 Xvfb 是否运行
pgrep -x Xvfb || Xvfb :99 -screen 0 1920x1080x24 -ac &

# 验证 DISPLAY
echo $DISPLAY  # 应为 :99
```

### 2. any-auto-register 服务状态

```bash
# 检查服务（注意端口可能是 8000 或 8001）
systemctl is-active any-auto-register || echo "Service not running"
ps aux | grep uvicorn | grep any-auto-register

# 查看服务环境
systemctl show any-auto-register -p Environment
cat /proc/$(pgrep -f uvicorn)/environ 2>/dev/null | tr '\0' '\n' | grep -E "PORT|HOST"
```

**注意**：服务可能运行在 **8001** 端口（`--port 8001`），API 端点需相应调整。

### 3. 数据库配置验证

```python
import sqlite3
import os

# 自动检测 any-auto-register 路径
any_auto_dir = os.getenv('ANY_AUTO_REGISTER_DIR', '/root/src/any-auto-register')
db_path = os.path.join(any_auto_dir, 'account_manager.db')

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查代理状态
cursor.execute("SELECT id, url, is_active FROM proxies")
proxies = cursor.fetchall()
print(f"代理: {proxies}")

# 检查接码平台
cursor.execute("SELECT provider_key, config_json FROM provider_settings WHERE provider_type='sms'")
cursor.fetchall()
```

### 自动化预检查脚本

```bash
# 一键验证所有环境依赖
python3 ~/.hermes/skills/automation/account-registration/scripts/preflight_check.py
```

脚本功能：
- Xvfb 安装状态检查
- Xvfb 运行状态检查
- DISPLAY 环境变量验证
- any-auto-register 服务状态
- 数据库连接与配置
- API 健康检查

> ⚡ **前置检查清单**：Xvfb 安装+运行 → DISPLAY 环境 → 服务状态 → 数据库连接 → 代理禁用 → 接码平台连接

### 验证并同步脚本

```bash
# 验证所有账号并同步到 9Router
python3 ~/.hermes/skills/automation/account-registration/scripts/validate_and_sync.py

# 指定账号
python3 ~/.hermes/skills/automation/account-registration/scripts/validate_and_sync.py --emails user1@example.com,user2@example.com
```

脚本功能：
- 查询本地数据库有完整 token 的账号
- 等待 2 分钟后验证（缓解 Cloudflare 封锁）
- 验证通过则刷新 token
- 自动同步到 9Router（按 email 去重）

> ⚠️ **9Router 数据库路径**：脚本默认 `/root/src/9router-data/db/data.sqlite`（v0.4.31+ SQLite），其他服务器需修改 `NINE_ROUTER_DB` 变量。同时需双写 `/root/src/9router-data/db.json` 作为备份。

---

## 标准注册流程

### 阶段 1：配置准备

```python
import sqlite3
import requests

def prepare_registration():
    # 1. 禁用代理
    conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE proxies SET is_active = 0 WHERE is_active = 1")
    conn.commit()
    conn.close()

    # 2. 设置 DISPLAY（headed 模式）
    import os
    os.environ.setdefault('DISPLAY', ':99')

    # 3. 验证接码平台配置
    # ... 查询 provider_settings 确认 sms_provider 存在
```

### 阶段 2：创建注册任务

```python
import requests
import json

# 方式 A：通过 any-auto-register API 创建任务
payload = {
    "platform": "chatgpt",          # 目标平台
    "count": 1,                     # 注册数量
    "concurrency": 1,
    "executor_type": "headed",      # 强制 headed 模式
    "proxy": None,                  # 禁用代理
    "captcha_solver": "auto",
    "extra": {
        "mail_provider": "cfworker_admin_api",  # 邮箱平台
        "sms_provider": "herosms",              # 接码平台
        "identity_provider": "mailbox",         # 邮箱注册
    }
}

resp = requests.post("http://localhost:8000/api/tasks/register", json=payload)
task_id = resp.json()["id"]

# 方式 B：通过 any-auto-register API（端口 8001）
# 注意：如果服务运行在 8001 端口，使用 http://localhost:8001
```

**任务监控**：
```python
import time

def monitor_task(task_id, poll_interval=10, timeout=1800):
    """监控注册任务直到完成"""
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"http://localhost:8001/api/tasks/{task_id}")
        if resp.status_code == 200:
            task = resp.json()
            status = task.get("status")
            progress = task.get("progress")
            success = task.get("success", 0)
            error_count = task.get("error_count", 0)
            print(f"[{time.strftime('%H:%M:%S')}] {progress} 成功:{success} 失败:{error_count}")
            
            if status in ("succeeded", "failed", "cancelled"):
                return task
        
        time.sleep(poll_interval)
    return None
```

**实践经验（2026-05-10）**：
- 6 个账号 headed 模式注册：成功 4 个，失败 2 个（约 67% 成功率）
- 失败原因：OAuth 流程中 `about_you 提交后未跳转` 或 `OAuth 验证码校验失败`
- 建议并发数 `concurrency=2` 平衡速度和资源消耗
- 批量注册建议分批次：每批 5-10 个，失败后检查日志决定是否重试
- 查看任务日志：`GET /api/tasks/{task_id}/events?limit=200`

**失败处理**：
- 检查任务 `result.errors` 了解失败原因
- `about_you 提交失败` 可尝试降低并发或检查 Xvfb 状态
- OAuth 失败可能需要重试整个批次

### 阶段 3：监控与结果

```python
import sqlite3
import time

task_id = "xxx"

def monitor_task(task_id, timeout=300):
    conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
    cursor = conn.cursor()
    
    start = time.time()
    while time.time() - start < timeout:
        cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
        status = cursor.fetchone()[0]
        
        if status in ['succeeded', 'failed', 'cancelled']:
            return status
        
        time.sleep(3)
    
    return 'timeout'
```

---

## 注册后验证与同步（9Router）

注册完成后，自动执行验证 → 刷新 token → 同步到 9Router 流程。

> 🔥 **ChatGPT/Codex 健康检查专项**：详见 `references/codex-health-check.md` — 正确的 OAuth client_id、直接 token 刷新流程、New API 路由测试、结果解读（含免费账号 429 的正确理解）。

### ⚠️ 前置条件检查（必须）

**在执行任何同步操作前，先验证凭证是否存在**：

```python
import sqlite3

conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
cur = conn.cursor()
cur.execute("""
    SELECT a.id, a.email, ac.key, ac.value
    FROM accounts a
    LEFT JOIN account_credentials ac ON a.id = ac.account_id
    WHERE a.platform = 'chatgpt'
    ORDER BY a.id, ac.key
""")
rows = cur.fetchall()

has_creds = {}
for row in rows:
    acc_id, email, key, value = row
    if acc_id not in has_creds:
        has_creds[acc_id] = {'email': email, 'has_token': False}
    if key in ('access_token', 'accessToken') and value:
        has_creds[acc_id]['has_token'] = True

conn.close()

# 检查结果
accounts_without_creds = [aid for aid, info in has_creds.items() if not info['has_token']]
if accounts_without_creds:
    print(f"⚠️  以下账号缺少凭证: {accounts_without_creds}")
    print("原因：ChatGPT 凭证可能未回写到 account_credentials 表")
    print("解决：1) 检查是否有其他凭证表 2) 重新走 OAuth 流程 3) 手动补充凭证")
    # 不要继续执行同步流程
```

**如果发现凭证缺失，跳转到【凭证缺失处理】（见下方章节）**。

### 前置条件

- **9Router v0.4.31+ 主数据库路径：`/root/src/9router-data/db/data.sqlite`**（SQLite 的 `providerConnections` 表 — 这是 9Router 实际读取的数据源）
- **`/root/src/9router-data/db.json` 仅为备份**，修改它不会影响 9Router 行为；必须同时更新 SQLite 和 db.json
- 9Router 进程运行中（`ps aux | grep 9router`）
- **凭证已确认存在**（见上方【前置条件检查】）

### 步骤 1：查询有完整 token 的账号

```python
import sqlite3
from sqlmodel import Session, text
from core.db import engine

with Session(engine) as sess:
    rows = sess.exec(text('''
        SELECT a.id, a.email,
          (SELECT ac.value FROM account_credentials ac
           WHERE ac.account_id=a.id AND ac.key='refresh_token' AND ac.value != '' LIMIT 1),
          (SELECT ac.value FROM account_credentials ac
           WHERE ac.account_id=a.id AND ac.key='id_token' AND ac.value != '' LIMIT 1),
          (SELECT ac.value FROM account_credentials ac
           WHERE ac.account_id=a.id AND ac.key='access_token' AND ac.value != '' LIMIT 1)
        FROM accounts a WHERE a.platform='chatgpt' ORDER BY a.id
    ''')).all()
    
    accounts = []
    for r in rows:
        if r[2] and r[3] and r[4]:
            accounts.append({"db_id": r[0], "email": r[1], "refresh_token": r[2], "id_token": r[3], "access_token": r[4]})
```

### 步骤 2：验证 token 有效性

使用 `curl_cffi` + `impersonate="chrome120"` 调用 `/backend-api/me`：

```python
from curl_cffi import requests as cffi_requests

for acct in accounts:
    session = cffi_requests.Session(impersonate="chrome120", proxy=None)
    resp = session.get(
        "https://chatgpt.com/backend-api/me",
        headers={"authorization": f"Bearer {acct['access_token']}", "accept": "application/json"},
        timeout=30
    )
    is_valid = resp.status_code == 200
```

**注意**：Cloudflare 封锁可能导致 403 错误。如果遇到大面积 403：
1. 等待 2-5 分钟后重试
2. 验证结果可能波动，多次采样取多数一致结果

### 步骤 3：刷新 token

对验证通过的账号调用 OAuth refresh endpoint：

```python
from platforms.chatgpt.token_refresh import TokenRefreshManager

manager = TokenRefreshManager(proxy_url=None)
result = manager.refresh_by_oauth_token(acct["refresh_token"])

if result.success:
    # 更新本地 DB
    with Session(engine) as sess:
        for key, val in [("access_token", result.access_token),
                         ("refresh_token", result.refresh_token or acct["refresh_token"]),
                         ("id_token", result.id_token or acct["id_token"])]:
            if val:
                sess.exec(text(
                    "UPDATE account_credentials SET value=:v, updated_at=CURRENT_TIMESTAMP "
                    "WHERE account_id=:aid AND key=:k"
                ).bindparams(v=val, aid=acct["db_id"], k=key))
        sess.commit()
```

**已知问题**：`token_refresh.py` 中 `Account` 类型注解导致 `NameError: name 'Account' is not defined`。

**根因**：`token_refresh.py` 将 `Account` 放在 `TYPE_CHECKING` 条件导入（第 16-17 行），但模块顶层**缺少 `from __future__ import annotations`**。Python 3.x 在函数签名中遇到 `account: Account` 时会求值注解，而 `TYPE_CHECKING` 在运行时为 `False`，导致 `Account` 未定义。

**修复（2026-05-23 应用）**：
```python
# 在 token_refresh.py 第 1 行 docstring 后、import 前添加
from __future__ import annotations
```

这告诉 Python **不要运行时求值注解**，从而消除 `NameError`。该修复同时适用于任何在 `TYPE_CHECKING` 下导入类型并在函数签名中使用的情况（`payment.py`、`plugin.py` 等）。

**如果遇到 `NameError: name 'Account' is not defined`**：
1. 先用 `from __future__ import annotations` — 这是最干净的修复
2. 如果模块 Python <3.7 不支持，降级方案：将 `account: Account` 改为 `account: "Account"`（字符串化注解）

**服务重启**：修改后需 `systemctl restart any-auto-register` 重新加载模块才能生效。

另见 `references/codex-token-reauthorization.md` 中关于 token 刷新路径的完整说明。

### 步骤 4：注入 9Router（双写 SQLite + db.json）

⚠️ **9Router v0.4.31+ 从 SQLite 读取数据，db.json 是备份。必须双写！**

> 🔥 **任何导入操作前，9Router 数据目录必须已初始化 Git 仓库**，用于追踪每次数据变更。导入后必须 `git diff` 确认只改动了预期条目，然后 `git commit`。详见 `references/git-tracking-9router-data.md`。

**`providerConnections` 表结构**：
- `provider` 和 `email` 是**独立列**，不在 JSON `data` 字段内
- 去重检查用 `WHERE email = ?`（列查询），不用 `json_extract(data, '$.email')`

```python
import json, uuid, sqlite3
from datetime import datetime, timezone

# ⚠️ 主数据源：SQLite providerConnections 表
SQLITE_DB = "/root/src/9router-data/db/data.sqlite"
JSON_DB = "/root/src/9router-data/db.json"

# 1. 读取现有连接（用 provider + email 列查询，不用 json_extract）
conn = sqlite3.connect(SQLITE_DB)
cur = conn.execute(
    "SELECT id, email, data FROM providerConnections WHERE provider = 'codex'"
)
codex_rows = cur.fetchall()
# 建立 email → (id, data) 映射用于去重和 UPDATE
email_map = {}
for row_id, email, data_str in codex_rows:
    email_map[email] = (row_id, json.loads(data_str))
conn.close()

# 2. 构建新连接数据并写入
for acct in valid_accounts:
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    new_id = str(uuid.uuid4())
    display_name = acct.get("name") or acct["email"].split("@")[0].capitalize()

    data = {
        "accessToken": acct["access_token"],
        "refreshToken": acct["refresh_token"],
        "idToken": acct.get("id_token", ""),
        "expiresAt": now,
        "displayName": display_name,
        "testStatus": "untested",
        "backoffLevel": 0,
        "consecutiveUseCount": 0,
        "proxyId": "iproyal-us-residential",
        "providerSpecificData": {
            "proxyPoolId": "iproyal-us-residential",
            "chatgptAccountId": acct.get("user_id", str(uuid.uuid4())),
            "chatgptPlanType": "free"
        },
        "lastUsedAt": None, "errorCode": None,
        "lastError": None, "lastErrorAt": None,
    }
    # 添加 null modelLock 字段（匹配现有连接格式）
    for m in ["gpt-5-codex", "gpt-5.1-codex", "gpt-5.2-codex", "gpt-5.3-codex",
              "gpt-5.4", "gpt-5.5", "qwen3-coder-next"]:
        data[f"modelLock_{m}"] = None

    conn = sqlite3.connect(SQLITE_DB)
    if acct["email"] in email_map:
        # UPDATE：保留 testStatus/backoffLevel 等 9Router 状态字段
        existing_id, existing_data = email_map[acct["email"]]
        existing_data.update({k: v for k, v in data.items()
                              if k in ("accessToken", "refreshToken", "idToken",
                                       "expiresAt", "displayName", "providerSpecificData")})
        conn.execute(
            "UPDATE providerConnections SET data=?, updatedAt=?, name=?, isActive=1 WHERE id=?",
            (json.dumps(existing_data), now, display_name, existing_id))
    else:
        # INSERT 新连接
        conn.execute(
            """INSERT INTO providerConnections
               (id, provider, authType, name, email, isActive, data, createdAt, updatedAt)
               VALUES (?, 'codex', 'oauth', ?, ?, 1, ?, ?, ?)""",
            (new_id, display_name, acct["email"], json.dumps(data), now, now))
    conn.commit(); conn.close()

# 3. 同步更新 db.json（镜像 SQLite 状态）
with open(JSON_DB, 'r') as f:
    db = json.load(f)
conns = db.get("providerConnections", [])
if isinstance(conns, dict):
    conns = list(conns.values())
# 追加或更新 db.json 中的对应条目
# ... update conns list ...
db["providerConnections"] = conns
with open(JSON_DB, 'w') as f:
    json.dump(db, f, indent=2, ensure_ascii=False)

# 4. Git 提交变更
# cd /root/src/9router-data && git add -A && git diff --stat
# git commit -m "import: add <email> (ChatGPT Codex)"

# 5. 重启 9Router 加载新连接
# systemctl restart 9router
```

> ⚠️ **SQLite WAL 模式**：INSERT/UPDATE 后的数据在 WAL 文件中，主 `data.sqlite` 文件 hash 可能不变。`git diff --stat` 可能只显示 `db.json` 变更——这是正常的，数据已在 SQLite 中，只是尚未 checkpoint。通过 SQL 查询可确认数据已写入。

### 步骤 5：消息发送测试（可选）

**当前状态**：服务器直连 ChatGPT 消息 API 存在困难。

**已知问题**：
- `POST /backend-api/conversation` 返回 `422 Invalid conversation body`，请求格式可能已变更或需要额外 Cookie
- Cloudflare 封锁（403）持续，即使使用 `curl_cffi` + `chrome120` 指纹

**建议**：
- 9Router 会处理实际的 API 调用，账号只需 token 有效即可
- 消息发送测试可暂缓，通过 9Router 实际使用验证

---

## 常见故障排查

### ⚠️ 凭证缺失（最常见）

**现象**：`account_credentials` 表中无 `access_token` 等字段，导致同步脚本跳过所有账号。

**诊断**：
```python
# 检查凭证数量
SELECT COUNT(*) FROM account_credentials WHERE key='access_token' AND value != '';
# 预期：大于 0
```

**根因**：
- ChatGPT 注册流程的 OAuth token 未回写到 `account_credentials`
- 账号通过非标准流程注册（手动、其他工具）
- 数据库权限问题导致写入失败

**解决**：见【凭证缺失处理】章节。

### Xvfb 与 headed 浏览器

**错误**：`BrowserType.launch: Failed to launch the browser process. Looks like you launched a headed browser without having a XServer running.`

**根因**：服务器无图形界面， headed 模式需要 Xvfb 提供虚拟显示。

**解法**：
```bash
# 安装
apt-get update && apt-get install -y xvfb

# 启动
Xvfb :99 -screen 0 1920x1080x24 -ac &

# 导出 DISPLAY
export DISPLAY=:99

# systemd 服务添加环境变量（持久化）
# 在 /etc/systemd/system/any-auto-register.service 中添加：
# Environment=DISPLAY=:99
systemctl daemon-reload && systemctl restart any-auto-register
```

### HeroSMS 国家代码无效

**错误**：`HeroSMS 获取号码失败: V2=NO_NUMBERS; V1=NO_NUMBERS`

**根因**：硬编码国家代码与实际 API 不匹配，或该国家无可用号码。

**诊断**：
```python
import requests, sqlite3, json

conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
cursor = conn.cursor()
cursor.execute("SELECT auth_json FROM provider_settings WHERE provider_key='herosms'")
api_key = json.loads(cursor.fetchone()[0])['herosms_api_key']

# 获取国家列表
countries = requests.get(
    "https://hero-sms.com/stubs/handler_api.php",
    params={"action": "getCountries", "api_key": api_key}
).json()

# 查找美国（可见的物理号）
usa = [c for c in countries if 'USA' in c.get('eng','') and c.get('visible')==1]
print(usa)
```

**正确值**：美国物理号 `187`，虚拟号 `12`（通常无库存）

### OAuth 验证码校验失败

**错误**：`OAuth 验证码校验失败: 验证码页提交后未跳转`

**根因**：验证码超时或页面状态异常，注册状态机对 OAuth 流程失败已实现自动重试。

**行为**：系统自动执行"全新浏览器 OAuth 重试"，无需人工干预，日志见 `browser_register.py: run_oauth_with_retry`。

### 🔥 OTP 验证码持续超时（pre-refresh bug）

**现象**：浏览器 OAuth 在 `email_otp_verification` 步骤卡住 120 秒后超时，日志显示 `"等待验证码超时 (120s)"`，但 cfworker 已收到验证码邮件。

**根因**：`_build_otp_callback` 中的 `otp_cb` 闭包在调用 `wait_for_code()` **之前**执行了 `_ids.update(_mb.get_current_ids(_ma))`，把刚到达的验证码邮件 ID 也加入了 `before_ids` 过滤集合。`wait_for_code` 按 `mid in seen` 过滤，新邮件被跳过。

**修复**（`plugin.py` `_build_otp_callback` → `otp_cb`）：移除 `wait_for_code` 前的 `_ids.update()` 调用，仅在 `wait_for_code` 返回后刷新 `_ids`。

详见 `references/codex-token-reauthorization.md`。

### FallbackMailbox 路由失败

**现象**：`RuntimeError: 未找到邮箱 provider 上下文`

**根因**：`create_mailbox()` 返回 `FallbackMailbox`，但其 `_resolve_mailbox()` 需要通过 `account.extra.mailbox_provider_key` 查找正确 provider。`_build_otp_callback` 创建的 `MailboxAccount` 未设置此字段。

**修复**：创建 `MailboxAccount` 后添加 `mail_acct.extra = {"mailbox_provider_key": provider_name}`。

### payment.py 缺少 Account 导入导致 NameError

**错误**：`NameError: name 'Account' is not defined`

**根因**：`platforms/chatgpt/payment.py` 中引用了 `Account` 类型，但仅保留了注释掉的旧导入 `# from ..database.models import Account`，未提供实际定义。

**修复**（必须在上游修复前手动 patch）：
```python
# 在 payment.py 第 13 行后添加
from core.base_platform import Account
```

**自动化修复脚本**：
```bash
python3 ~/.hermes/skills/automation/account-registration/scripts/fix_payment_import.py
```

**影响范围**：`fetch_subscription_status_details()`、`generate_plus_link()`、`generate_team_link()` 等所有使用 `Account` 类型注解的函数。

**检测**：任何调用 `from platforms.chatgpt.payment import fetch_subscription_status_details` 的操作都会触发此错误。

---

## 已知问题（截至 2026-05-10）

### HeroSMS 接码 — add-phone 页面交互绕过 CF ✅（2026-05-27 已攻克）

**现象**：HeroSMS 虚拟号能租到（余额 $8.835），但 OpenAI `add-phone/send` 返回 400 + body=`{`——**即使通过美国/加拿大住宅代理 IP 也照拒**。

**根因**：Cloudflare JS Challenge 拦截 `_browser_fetch()` 的独立 XHR 请求。浏览器正常页面能过 CF，但 `add-phone/send` 端点有更严格保护。

**✅ 已应用修复**：用键盘 `Tab+Enter` 触发原生表单提交 + SPA 同页 OTP 检测。浏览器原生表单提交携带完整 CF 上下文可通过。提交记录 `0dff59d` + `e168ce5`。详见 `references/add-phone-cloudflare-block.md`。

**关键代码变更**（`platforms/chatgpt/browser_register.py`）：
- `_handle_add_phone_challenge()`：移除 `_browser_fetch()` 调用，改用 `page.fill()` + `page.keyboard.press("Tab")` + `page.keyboard.press("Enter")`
- `_fill_and_submit_phone()`：新函数，查找 phone input → 填号 → Tab+Enter 提交 → 等待 OTP 输入框（SPA 同页检测）或页面跳转 → 错误检测 → 页面内容 dump
- `_find_otp_input()`：新函数，多选择器 fallback 查找 OTP 验证码输入框
- `_request_openai_resend()`：重写为点击页面重发按钮（fallback 为重新导航到 add-phone 再提交）

**⚠️ SMS 提供商对 OpenAI 的现状（2026-05-28）**：

| 提供商 | 状态 | 原因 |
|--------|------|------|
| **TextVerified** | ✅ 默认 | 物理 SIM 号，12 秒收码，$0.50/次，已实测通过 |
| **5sim** | ❌ 不适用 | 全球仅 virtual51/virtual63 虚拟号（0 个物理运营商） |
| **HeroSMS** | ❌ 不适用 | 同上，所有号码被 OpenAI 静默拒绝 |
| **SMS-Activate** | ❌ 已关站 | 2025-12-29 宣布关闭，官网确认 |

**结论**：✅ **TextVerified 已集成并实测通过**——物理 SIM 号，12 秒收码，$0.50/次。5sim/HeroSMS 对非 OpenAI 服务（Telegram/WhatsApp/Google）仍可用。

**5sim 集成状态**：`FiveSimProvider` 已完整实现于 `core/base_sms.py`（~200 行），通过 `create_sms_provider('fivesim_api', config)` 创建，API 端点 `GET /v1/user/buy/activation/{country}/{operator}/{product}`、`GET /v1/user/check/{id}`、`GET /v1/user/cancel/{id}`。Bearer Token (JWT) 认证。数据库 `provider_definitions` 和 `provider_settings` 已配置，API key 存于 `auth_json.fivesim_api_key`。默认 disabled（HeroSMS 仍是默认），通过 `extra.sms_provider: "fivesim"` 显式指定。

| 国家 | 运营商 | 结果 |
|------|--------|------|
| 🇺🇸 美国 (country=187) | ote (虚拟号) | ❌ SMS 永不抵达 |
| 🇨🇦 加拿大 (country=36) | ote (虚拟号) | ❌ 95秒超时→重发→仍无 SMS |
| 🇺🇸 美国 (country=187) | **Verizon (物理号)** | ❌ 同样收不到 |

HeroSMS **整条线被 OpenAI 静默拒绝**（可能所有号码都被标记为虚拟/VoIP）。**结论：HeroSMS 不可用于 OpenAI 注册。** 代码中已有 SMS-Activate provider 支持，也可集成 5sim、SMSPool。

#### HeroSMS operator 参数（2026-05-27 新增）

为缓解号码质量问题，已在 `HeroSmsProvider` 和 `_request_number_raw()` 中添加 `operator` 参数支持物理运营商号码。`getNumberV2` API 按 `verizon → tmobile → att → 无operator fallback` 顺序尝试。配置 key：`herosms_operator`（不配置时默认按上述顺序）。实测：Verizon ($0.15)、T-Mobile ($0.1973) 可正常租号，AT&T 无库存。提交记录 `5572e31`。详见 `references/herosms-api.md`。

### ChatGPT 注册流程改版（2026-05-21）✅ 已修复

**现象**：所有 ChatGPT headed 注册全部失败，错误从 `about_you 提交后未跳转` 逐步变为 `未支持的注册状态: platform_welcome`。

**根因**：ChatGPT 改版了注册后流程——about_you 提交后跳转到 `platform.openai.com/welcome?step=create` 而非过去的 OAuth callback URL。三处代码需适配，外加 HeroSMS 配置缺失。

**修复**（已在 `browser_register.py` + `helpers.py` 应用 5 处 patch，详见 `references/chatgpt-may-2026-registration-changes.md` 和 `references/herosms-build-phone-callbacks-fix.md`）：
1. about_you 提交成功检测添加 `platform.openai.com`
2. `_infer_page_type` 添加 `platform_welcome` / `platform_page`
3. 主状态机添加 platform_welcome 为终态直接返回
4. add_phone 短信失败后 fallthrough 到跳过逻辑（而非 `return None`）
5. `build_phone_callbacks` 移除无 definition 时的 `dict(extra)` 回退

**验证**：2026-05-21 成功注册 1 个账号（完整 OAuth + 手机验证），批量 8 个运行中。

### 🔥 add_phone 跳过死循环（2026-05-26 发现并修复）

**现象**：ChatGPT headed 注册在 OAuth 流程中无限循环。日志模式：
```
step 5: email_otp_verification → 获取验证码 → 提交成功
step 6: add_phone → SMS 租号失败 → "尝试跳过 add_phone"
  跳过后页面状态: -          ← 页面类型为空！
→ continue 回到 OAuth 状态机 → login_email → OTP → add_phone → ...
```
任务进度卡在 `0/5`，浏览器一直跑但产不出任何账号。

**根因**：跳过 add_phone 后 `_derive_registration_state_from_page()` 返回空 `page_type`，代码没命中 `login_email` 分支也没命中 `add_phone` 分支，走了 `else: continue` 回到状态机循环。

**修复**（`browser_register.py` `_do_codex_oauth` 跳过 add_phone 后）：
```python
elif not skip_state.get("page_type"):
    # 页面状态为空，跳过 add_phone 后无法识别页面 → session 已失效
    log("  跳过 add_phone 后页面状态未知，放弃当前 OAuth 避免死循环")
    return None
```
在 `login_email` 检测前插入空 page_type 检测，直接 `return None` 终止当前 OAuth，由外层用全新浏览器重试。

**更深层问题**：SMS 租号失败不是因为 HeroSMS 余额不足或 API 不可用（API 完全正常，余额 $8+，库存充足），而是因为 **`provider_definitions` 表缺少 SMS provider 条目**。

**`provider_definitions` 缺失 SMS 条目**：
- `_resolve_sms_provider_for_task()` 需要从 `provider_definitions` 表查询 SMS provider 定义（`get_by_key("sms", "herosms")`）
- 如果该表无 SMS 条目，返回 None → fallback 空 dict → `herosms_api_key` 丢失 → 租号失败
- 症状：日志中 `activation_id` 已生成但立即失败，「未获取到手机号」
- 修复：在 `provider_definitions` 表中插入 herosms 条目（provider_type='sms', provider_key='herosms', driver_type='hero_sms', default_auth_mode='api_key'）

**诊断命令**：
```bash
# 检查 provider_definitions 表
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
rows = conn.execute(\"SELECT id, provider_type, provider_key FROM provider_definitions\").fetchall()
print('provider_definitions:', rows)
# 至少应有一条 provider_type='sms' 的记录
"

# 检查 HeroSMS 余额（验证 API 可用性）
curl -s "https://hero-sms.com/stubs/handler_api.php?api_key=KEY&action=getBalance"

# 查看实时任务日志
journalctl -u any-auto-register -f --no-pager | grep -E 'task:|OAuth state|add_phone|跳过|验证码'
```

### 🔥 account_selection → add_phone 循环（2026-05-26 发现，CF 已修复，SMS 仍未解决）

**现象**：修复 add_phone 死循环后，出现新循环——OAuth 流程不再回 OTP，但在 account_selection 和 add_phone 之间循环。

**2026-05-28 新发现 — 虚拟号特有失败模式**：

```
手机号提交 → Enter → OTP 输入框出现（OpenAI 形式上接受号码）
→ 5sim/HeroSMS 轮询等 SMS → 永远收不到 → 3分钟后超时
→ 跳过 add_phone → 回到 account_selection → 再进 add_phone
→ 用同一个 activation_id 重试（不重复租号）→ 继续收不到 → 循环
```

这与之前的"号码被拒绝"不同——OpenAI **接受**了号码格式，但虚拟号无法接收 OpenAI 发出的 SMS。详见 `references/sms-provider-landscape.md`。

```
step[1] account_selection → 点击目标账号
step[2] account_selection → 页面没走，再次点击超时 → 掉到 add_phone
step[3] add_phone → 租号成功 → 提交 → 跳过 → 回到 account_selection
```

**根因拆解**（两部分）：

1. **Cloudflare 拦截 add-phone API** ✅ **已修复（2026-05-27）**
   - `_browser_fetch()` 发的 `add-phone/send` 请求被 CF JS Challenge 拦截 → 400
   - 修复：`page.fill()` + `Tab+Enter` 原生表单提交 → OTP 输入框出现 ✅
   - 提交记录：`0dff59d`、`e168ce5`

2. **SMS 未送达** ❌ **HeroSMS 整条线不可用于 OpenAI**
   - CF 绕过成功后 OTP 输入框已出现，但 HeroSMS 收不到验证码
   - 已验证：美国 (187) + CA代理、加拿大 (36) + CA代理 — 均失败
   - 结论：HeroSMS 号码（全虚拟号）被 OpenAI 静默拒绝
   - 解决：需换 SMS 提供商（5sim、SMSPool、SMS-Activate 等）

### 任务卡在 cancel_requested — 强制清理

**现象**：通过 Web UI 取消任务后，状态一直 `cancel_requested`，队列被堵，新任务 `pending`。

**根因**：取消 API 设置状态标志，但任务在阻塞操作（等待 SMS、浏览器交互）中无法检查取消标志。

**强制清理**：
```python
import sqlite3
conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
# tasks 表主键是 id 不是 task_id
conn.execute("UPDATE tasks SET status='failed', error='Force cancelled by admin' WHERE id=?", (task_id,))
conn.commit(); conn.close()
# 然后重启服务清空内存队列
# systemctl restart any-auto-register
```

> ⚠️ 重启会中断所有 `pending` 任务，需确认没有正常的等待任务。详见 `references/force-cancel-stuck-task.md`。

### OpenAI Codex Refresh Token 一次性轮换

**关键事实**：OpenAI/Codex 使用**一次性轮换 refresh token**——用一次就废，同时发新 RT。如果新 RT 没保存成功，旧 RT 也不可再用。

**影响**：
- 多个 9Router 连接共享同一个 RT：第一个刷新成功，其余全部失效
- 9Router 自动刷新消耗了 RT 但新 RT 未持久化 → 账号不可恢复
- 唯一恢复路径：完整 OAuth 重新认证

**检测**：刷新端点返回 `HTTP 401: "Your refresh token has already been used to generate a new access token. Please try signing in again."` 即表示 RT 已消费。

### Kiro 新注册账号凭证缺失（2026-05-12）

**现象**：API 注册的 Kiro 账号只有 `accessToken` + `legacy_token`，缺 `refreshToken` / `clientId` / `clientSecret`。  
**根因**：注册流程未执行 device auth（`step12f_device_auth`）。  
**影响**：三步验证 token 刷新无法进行。详见 `references/kiro-kiro-credential-gap.md`。  
**降级**：验证脚本支持 accessToken 直接查询 AWS Q API。

### 代理池迁移（2026-05-12）

从 systemd env var 全局代理 → proxyPools/proxies 表统一管理：添加记录 → 分配连接 → 移除 env var → restart。

### `check_valid()` 误判有效账号为 invalid

**现象**：Web UI 显示账号状态 `invalid`，但手动验证账号有效。

**根本原因**：`proxy_pool.get_next()` 在服务刚启动或代理池清空后返回 `None`，导致 `proxy=None` 路径失败（尽管 `fetch_subscription_status_details()` 内部使用 `curl_cffi`，理论上应成功，但实际运行中 `account.extra` 字段可能不完整导致异常）。

**代码路径**：
```python
# plugin.py check_valid() 第 86-115 行
proxy_candidates = []
if configured_proxy:
    proxy_candidates.append((configured_proxy, False))
else:
    pooled_proxy = proxy_pool.get_next(region=region)  # 服务刚启动时 pool 为空 → None
    if pooled_proxy:
        proxy_candidates.append((pooled_proxy, True))
proxy_candidates.append((None, False))  # ← 直接请求

for proxy, should_report in proxy_candidates:
    try:
        details = fetch_subscription_status_details(a, proxy=proxy)
        ...
        return status not in ("expired", "invalid", "banned", None)
    except Exception:
        continue  # ← 所有异常被静默吞掉
return False
```

**为什么手动测试成功**：直接调用 `check_valid()` 时 `account.extra` 字段完整，`fetch_subscription_status_details(a, proxy=None)` 通过 `curl_cffi` 成功返回 `free` → `True`。

**真正的 bug**：
1. 生命周期管理器构建的 `Account` 对象可能缺少 `extra` 字段（实际测试中此假设不成立）
2. `except Exception: continue` 吞掉了所有异常，包括 `fetch_subscription_status_details()` 可能抛出的任何错误（网络、JSON 解析、字段缺失等）
3. 代理池中的坏代理会导致第一次尝试失败，虽然 `should_report=False` 时不会 `report_fail`，但 `continue` 会正常进入下一轮

**修复方案**（待上游实施）：
1. **短期**：确保 `proxy_pool` 始终有可用代理，或在 `check_valid()` 中添加重试逻辑
2. **中期**：在 `should_report=False` 的 fallback 路径也加入错误日志，不要静默吞掉异常
3. **长期**：重构 `fetch_subscription_status_details()` 内部始终用 `curl_cffi`，与 proxy 无关；`account.extra` 缺失时降级到 `account.token`

**详细调试记录**：`references/check_valid_debug_2026-05-09_session2.md`

**当前状态**：所有 7 个 ChatGPT 账号实际均有效（free plan），但 Web UI 需要等待 bug 修复或手动触发检查刷新。

**详细调试记录**：`references/check_valid_debug_2026-05-09_session2.md`

### ChatGPT API 必须使用 curl_cffi

**问题**：`requests` 库调用 ChatGPT API 返回 403（Cloudflare 拦截）。

**正确方式**：
```python
from curl_cffi import requests as cffi_requests

resp = cffi_requests.get(
    "https://chatgpt.com/backend-api/me",
    headers={"Authorization": f"Bearer {token}"},
    impersonate="chrome110"  # 必须指定浏览器指纹
)
```

**受影响的 API**：
- `/backend-api/me` — 用户信息
- `/backend-api/conversations` — 对话列表
- `/backend-api/conversation` — 发送消息
- `/backend-api/wham/usage` — 使用量查询

### Cloudflare 封锁（2026-05-10 新增）

**现象**：服务器直连 ChatGPT API 时，大量请求返回 HTTP 403，错误信息 `"Unusual activity has been detected from your device"`。

**影响**：
- 验证阶段部分账号间歇性失败（波动性）
- 消息发送测试持续失败
- 同一 IP 短时间内大量请求会触发封锁

**缓解措施**：
1. 等待 2-5 分钟让封锁缓解
2. 使用 `curl_cffi` + `impersonate="chrome120"` 模拟真实浏览器
3. 增加请求间隔，避免短时间内大量请求
4. 优先通过 9Router 使用，不直接调用 ChatGPT API

**验证建议**：多次采样，取多数一致结果。若验证波动大，以最新一次为准。

### Proxy Pool 空值导致降级失败

**问题**：服务重启后 proxy pool 为空 → `proxy=None` → `requests` 调用失败。

**缓解措施**：在 `check_valid()` 中确保 fallback 路径也使用 `curl_cffi`，或预先填充代理池。

## Codex / ChatGPT Token 重新授权

当 9Router 中 Codex 连接的 accessToken 全部过期时，需通过 any-auto-register 重新授权。any-auto-register 的 `codex_refresh` action 内置 **3 条自动降级路径**（见 `platforms/chatgpt/plugin.py` `_execute_platform_action` → `action_id == "codex_refresh"`）：

```
路径1: refresh_token → OAuth API 刷新           (9Router 默认路径)
    ↓ 失败（Auth0 rotation 已消费旧 RT）
路径2: session_token → 静默 PKCE 换 id_token    (需账号有有效 session_token)
    ↓ 失败（大多数账号无 session_token）
路径3: email+password → Camoufox 浏览器完整 OAuth  (需 headed 环境)
```

### 前置条件（路径3）

- **密码必须存在**：`accounts.password` 不为空
- **Xvfb 运行**：`DISPLAY=:99`，headed 浏览器需要虚拟显示
- **代理可用**：浏览器通过代理访问 ChatGPT，推荐 IPRoyal US 代理
- **OTP callback**：如果登录触发邮箱验证，需 `provider_accounts` 正确关联 cfworker 邮箱

### 批量重新授权

```bash
# 通过 any-auto-register API 触发 codex_refresh
for ACCT_ID in $(python3 -c "
import sqlite3
conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
ids = conn.execute(\"SELECT id FROM accounts WHERE platform='chatgpt' AND password != ''\").fetchall()
print(' '.join(str(r[0]) for r in ids))
conn.close()
"); do
  curl -s -X POST "http://localhost:8000/api/actions/chatgpt/${ACCT_ID}/codex_refresh" \
    -H 'Content-Type: application/json' \
    -d '{"proxy": "http://USER:PASS_country-us@geo.iproyal.com:12321"}'
  sleep 2  # 间隔避免并发竞争
done
```

### 任务监控

```bash
# 查看所有 platform_action 任务状态
curl -s "http://localhost:8000/api/tasks?status=pending,running" | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f'Pending/Running: {len(d.get(\"items\",[]))}')"

# 已完成任务
curl -s "http://localhost:8000/api/tasks?status=succeeded,failed" | python3 -c "
import sys,json; d=json.load(sys.stdin)
for t in d.get('items',[]):
    print(f\"{t['task_id'][:20]}... {t['status']:10s} {t.get('error','')[:60]}\")"
```

### 已知限制（2026-05-23 更新 — 批量 16 账号全部成功）

- ~~**路径3 返回 Auth0 平台 token**~~ ✅ **已修复**：`_codex_refresh_via_browser_oauth` 已重写——OAuth 完成后导航到 `chatgpt.com` 并通过 `fetch('/api/auth/session')` 获取 session access_token，同时提取 cookies。**如 `/api/auth/session` 不可用（headless 浏览器限制），回退到 OAuth access_token——9Router 用 `refreshToken` 自行刷新，不依赖此 token。**
- ~~**refresh_token 未刷新**~~ ✅ **已修复**（批量 16/16 验证通过）：修复 OTP pre-refresh bug 后，路径3 完整 OAuth 能产出新的 `refresh_token` + `id_token` + `cookies`。单账号 90-180 秒完成。OAuth refresh 端点验证（`auth.openai.com/oauth/token`）→ 200 OK，refresh_token 完全有效。
- **`/api/auth/session` 返回空 accessToken**（不影响 9Router）：headless Camoufox 中 `fetch` 返回 HTTP 200 但 body 不含 `accessToken`，回退到 OAuth access_token。9Router 使用 `refreshToken` 通过 OAuth 端点自行刷新，不需要 session access_token。
- **`session_token` cookie 未获取**（不影响 9Router）：chatgpt.com 加载后 cookies 中无 `__Secure-next-auth.session-token`。9Router Codex 连接不需要此 cookie。
- **ChatGPT 网页 API Cloudflare 拦截**：IPRoyal 代理 IP 访问 `chatgpt.com/backend-api/me` 返回 403。不影响 Codex——Codex 通过 `auth.openai.com` OAuth 端点刷新，不经过 chatgpt.com。

### Auth0 Refresh Token 一次性轮换（重要）

OpenAI/Codex 使用 **Auth0 refresh token rotation**——每次刷新成功后旧 RT 立即失效，同时下发新 RT。多个进程/连接共享同一 RT 时，第一个刷新成功，其余全部失败。

**错误特征**：
```
HTTP 401: "Your refresh token has already been used to generate a new access token. 
Please try signing in again."
```

**唯一恢复路径**：完整 OAuth 重新认证（路径3）。

### OTP Callback 邮箱关联陷阱

`_build_otp_callback` 从 `provider_accounts` 表取**第一条**邮箱记录。如果账号有多个 provider_account（如旧邮箱 + 新邮箱），可能取到不再有效的邮箱，导致 OTP 获取失败，浏览器 OAuth 在邮箱验证步骤卡住。

**检测**：日志中出现 `"构建 OTP callback 失败: 未找到邮箱 provider 上下文"`。

**修复**：清理 `provider_accounts` 表中的过期记录，确保正确的 cfworker 邮箱排在第一条，或修改代码选择正确的 provider_account。

### 消息发送 API 格式问题（2026-05-10 新增）

**现象**：`POST /backend-api/conversation` 返回 `422 Invalid conversation body`。

**尝试过的格式**：
```python
# 格式1
{"messages": [{"role": "user", "content": "OK"}]}
# 格式2
{"messages": [{"role": "user", "content": "OK"}], "model": "auto"}
# 格式3
{"action": "next", "messages": [...], "parent_message_id": "..."}
# 全部失败
```

**可能原因**：
1. API 已变更，需要不同的请求结构
2. 需要额外的 Cookie 或 Header（如 `__cf_bm`）
3. 账号需要绑定支付方式或完成其他验证

**建议**：暂缓消息发送测试，通过 9Router 实际使用验证账号可用性。

---

## 凭证缺失处理（重要）

### 问题描述

any-auto-register 中 `accounts` 表有记录，但 `account_credentials` 表中**没有任何凭证字段**（access_token、refresh_token、id_token 均为空）。

### 诊断流程

**1. 确认凭证确实缺失**
```python
import sqlite3
conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM account_credentials WHERE key='access_token' AND value != ''")
count = cur.fetchone()[0]
conn.close()
print(f"有 access_token 的凭证记录: {count}")
```

**2. 检查是否有其他凭证表**
```python
conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cur.fetchall()]
print(f"所有表: {tables}")
conn.close()
```

**3. 检查 any-auto-register Web UI**
访问 `http://localhost:8000`，查看账号详情是否显示 token 已保存。

**4. 对比 9Router 已导入账号**
如果 9Router 中已有同邮箱的 Codex 账号，检查其凭证来源（可能是手动或其他脚本）。

### 解决方案

**方案 A：直接从外部来源导入到 9Router（推荐）**

如果账号在浏览器、其他数据库或文件中有凭证，绕过 any-auto-register：
```python
# 手动构建 9Router 连接条目
# 需要提供：email, accessToken, refreshToken, displayName
```

**方案 B：通过 any-auto-register 重新注册**

删除无效账号记录，重新走注册流程：
```python
# 1. 删除无凭证的账号
conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
cur = conn.cursor()
cur.execute("DELETE FROM accounts WHERE id = ? AND platform = 'chatgpt'")
conn.commit()
conn.close()

# 2. 重新执行注册流程（见上方标准注册流程章节）
```

**方案 C：手动补充凭证到 any-auto-register**

如果凭证在其他地方，手动插入到 `account_credentials` 表：
```sql
INSERT INTO account_credentials (account_id, credential_type, key, value, created_at, updated_at)
VALUES (?, 'token', 'access_token', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
```

然后使用标准同步流程。

### 已知环境差异

**此环境（/root/src/any-auto-register）**：
- ChatGPT 账号有 13 个，但均无凭证
- 已导入的 5 个 Codex 账号有完整凭证，但**不是从 any-auto-register 同步的**
- `chatgpt-account-sync` 技能的标准流程在此环境**无法直接执行**

**建议工作流**：
1. 先诊断凭证来源
2. 如果凭证在别处，使用**方案 A**
3. 如果需要重新获取凭证，使用**方案 B**
4. 不要强行运行标准同步脚本，它会因凭证缺失而跳过所有账号

---

## 数据库关键表

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `accounts` | 账号主表 | platform, email, password, user_id |
| `tasks` | 注册任务 | status, result_json, error |
| `task_events` | 任务日志 | level, message, detail_json |
| `proxies` | 代理池 | url, is_active, success_count |
| `provider_settings` | 第三方服务配置 | provider_type, provider_key, config_json, auth_json |
| `platform_capabilities` | 平台能力声明 | platform_name, capabilities_json |

---

## 架构要点

- **架构模式**：DDD 分层（api → application → domain → infrastructure）
- **插件系统**：`@register` 装饰器 + `core/registry.py` 动态加载
- **注册流程分发**：根据 `executor_type` 分为 `protocol` / `headless` / `headed`
- **OAuth 获取**：ChatGPT 注册后通过 Codex CLI OAuth 流程获取 `access_token`
- **并发执行**：通过 `services/task_runtime.py` 管理，SSE 实时日志推送到前端
- **账号同步到 9Router**：注册完成后，使用 `chatgpt-account-sync` 技能将有效账号注入 9Router

---

## Kiro 账号验证（平台专项）

Kiro 账号使用 **AWS Builder ID OIDC** 认证体系，与 ChatGPT OAuth 完全不同。

### ⚠️ 验证铁律（2026-05-26）

**绝对不能用以下端点作为「可用」的判定依据**：

| 端点 | 假阳性原因 |
|------|-----------|
| `ListAvailableModels` | 返回 200 + 模型列表 ≠ 对话服务可用（不同 AWS 服务） |
| `getUsageLimits` | 返回 200 + 额度数据 ≠ 对话服务可用 |
| `/chat` | 永远返回 200 + `UnknownOperationException` — 对非法请求也 200 |
| 仅判 `bool(access_token)` | token 存在 ≠ 账号未被封 — **0/45 真实可用 vs 45/45 假阳性** |

**唯一权威验证**：POST `generateAssistantResponse` 发送 `"Hi"`，解析返回的真实 AI 回复。只有返回正常回复内容（非 403、非 `UnknownOperationException`）才能判定为「可用」。

### 正确三步验证法

1. **Token 刷新** — POST `oidc.us-east-1.amazonaws.com/token`（`refreshToken` + `clientId` + `clientSecret`）
2. **使用量查询** — GET `q.us-east-1.amazonaws.com/getUsageLimits`
3. **🔥 真实对话测试（必须）** — POST `q.us-east-1.amazonaws.com/generateAssistantResponse`，发送 `"Hi"`，验证返回内容是否包含正常 AI 回复

> ⚠️ **所有账号无论有无 refreshToken 都必须经过步骤 3**。无 refreshToken 的账号用现有 accessToken 直接测试对话——不能跳过。
>
> **2026-05-26 实测**：45 个 Kiro 账号，25 个能正常刷新 token + 查询额度，但 **0 个能通过生成对话测试**——全部 403。之前"100% 有效"的报告完全是假阳性。详见 `references/kiro-account-status-2026-05-26.md`。

### 前置条件

| 凭证 | 必须 | 说明 |
|------|------|------|
| `refreshToken` | ✅ | 无此凭证 → 账号标记为「未测试」，不能标「有效」 |
| `clientId` | ✅ | OAuth client ID |
| `clientSecret` | ✅ | JWT 私钥（以 `eyJraW...` 开头） |
| `accessToken` | 可选 | 单独不足以验证账号有效性 |

### 快速运行

```bash
# 运行验证脚本（已移入 scripts/ 并加 kiro- 前缀）
python3 ~/.hermes/skills/automation/account-registration/scripts/kiro-check_kiro_accounts.py

# 测试 Chat API（权威验证）
python3 ~/.hermes/skills/automation/account-registration/scripts/kiro-test_chat_api.py --proxy http://100.64.247.23:7890

# 诊断 freeTrial 配额
python3 ~/.hermes/skills/automation/account-registration/scripts/kiro-diagnose_kiro_quota.py --ids 22,23,24
```

### freeTrial 配额行为

- **两档账号**：有 freeTrial（base 50 + freeTrial 500 = 550）vs 无 freeTrial（base 50）
- **服务器控制**：`freeTrialInfo` 是 AWS 侧账号属性，**无法通过登录激活**
- **注册时间规律**：2026-05-07 前注册的有 freeTrial，05-08 后的没有（500 freeTrial 是已停用的促销活动）
- 详见 `references/kiro-kiro-pricing-policy.md` 和 `references/kiro-kiro-login-quota-behavior.md`

### OTP 自动化（qhvip.cc）

仅 `@qhvip.cc` 邮箱支持通过 CF Worker API 自动获取 OTP。CF Worker 偶尔会因 DNS 记录丢失或自定义域名绑定失效而不可用，需按 `references/cfworker-email-recovery.md` 恢复。

**恢复后同步数据库**：`provider_settings.config_json.cfworker_api_url` 和所有 `provider_resources.metadata_json.api_url` 需从 `temp-email.khchen1985.workers.dev` 更新为 `https://mail.qhvip.cc`。

```python
from kiro_otp_callback import build_otp_callback
cb = build_otp_callback("user@qhvip.cc")
code = cb()  # 阻塞最多 120s
```

登录方法对比：**仅 `KiroBrowserLogin` 有效** — protocol 路径 (`login_for_tokens`) 获取 OTP 后 AWS 返回 400。详见 `references/kiro-kiro-otp-automation.md`。

### 常见错误速查

| 错误 | 原因 | 修复 |
|------|------|------|
| HTTP 401 Unauthorized | refreshToken 过期或 client 凭证错误 | 重新认证 |
| HTTP 429 | AWS 限流 | 等待后退避重试 |
| `getUsageLimits` 返回 totalLimit=0 | 用了 POST 而非 GET — POST 返回 200 但无数据 | 必须用 **GET** |
| 缺少 `refreshToken`/`clientId`/`clientSecret` | 注册未执行 device auth | 重新走完整 OAuth 流程 |
| CodeWhisperer 403 | 正常 — 不代表账号失效 | 用 `generateAssistantResponse` 重新测试 |
| `/chat` 返回 200 但无内容 | **假阳性** — body 是 `UnknownOperationException` | 永远用 `generateAssistantResponse` |
| Camoufox 代理 `NS_ERROR_PROXY_AUTHENTICATION_FAILED` | 代理 URL 含特殊字符（如 `_country-us`）被 Camoufox 错误解析 | 改用 `{"server":"host:port","username":"u","password":"p"}` 格式 |
| Camoufox `screen` 参数 `is_set` 报错 | Camoufox 版本不支持 dict 格式 screen | 移除 screen 参数 |
| OIDC Client 注册 `Invalid start url` | `issuerUrl` 用了错误地址 | 必须用 `https://view.awsapps.com/start` |
| OIDC 授权 scopes 不匹配 | 用了 `openid` 等标准 scope | 必须用 `codewhisperer:*` 系列 |

### 浏览器重新登录（恢复已失效的 refreshToken）

对没有 refreshToken 的账号，唯一恢复路径是 headed Camoufox OAuth 重登：

```bash
# 单个账号重登
.venv/bin/python3 scripts/kiro-browser-relogin.py <account_id>

# 批量重登（所有无 RT 的 kiro 账号）
.venv/bin/python3 scripts/kiro-batch-relogin.py
```

前提：Xvfb `:99` 运行中、IPRoyal US 代理可用、qhvip.cc CF Worker 邮箱 API 正常。
| Camoufox 代理 `NS_ERROR_PROXY_AUTHENTICATION_FAILED` | 代理 URL 格式不被 Camoufox 支持 | 拆分为 `server` / `username` / `password`（见 `references/kiro-browser-relogin.md`） |

### 平台特性

- OIDC 端点：`oidc.us-east-1.amazonaws.com`（单区域，全局）
- Usage API 有 US（`q.us-east-1`）和 EU（`q.eu-central-1`）端点
- Impersonation headers（`aws-sdk-rust/...`）必须携带，否则 AWS 拒绝
- Token 生命周期约 1 小时，`refreshToken` 每次刷新可轮换
- `clientSecret` 是 JWT 私钥，`accessToken` 以 `aoaAAAAAGn...` 开头

### 新平台评估

### NVIDIA NIM 平台

NVIDIA NIM 是当前发现的最优质免费账号来源——仅需邮箱注册，完全免费，提供 50+ LLM 模型。any-auto-register 可以批量注册，参考 Tavily 平台插件模板实现浏览器自动化注册。

> 详见 `references/nvidia-nim-registration-feasibility.md` — 注册流程、反爬分析、插件开发模板、风险评估

---

## 相关参考资料

- `references/kiro-kiro-api-architecture.md` — ⚠️ **关键**：Q Chat API vs CodeWhisperer 是两个独立 AWS 服务
- `references/kiro-kiro-api-details.md` — AWS OIDC 和 Q API 请求/响应详情
- `references/kiro-kiro-credential-gap.md` — 新注册账号凭证缺失问题
- `references/kiro-kiro-login-quota-behavior.md` — 登录尝试结果 & freeTrial 服务器端控制
- `references/cfworker-email-recovery.md` — ⚠️ CF Worker 邮箱 DNS/Worker 故障恢复流程（mail.qhvip.cc 宕机修复）
- `references/kiro-kiro-otp-automation.md` — CF Worker 邮箱 API 和 OTP 提取模式
- `references/kiro-kiro-pricing-policy.md` — Kiro/Amazon Q Developer 定价结构
- `references/kiro-chat-api-endpoint-discovery.md` — ⚠️ **关键**：`/chat` 端点假阳性（2026-05-26 已更正）
- `references/kiro-chat-api-vs-codewhisperer.md` — 两个 API 的区别和陷阱
- `references/kiro-camoufox-proxy-pitfalls.md` — ⚠️ Camoufox 代理格式陷阱（`_country-us` 需拆字段、`screen` 参数报错等）
- `references/kiro-account-status-2026-05-20.md` — 账号状态历史快照
- `references/kiro-kiro-api-modes.md` — Kiro API 模式详解
- `references/kiro-account-status-2026-05-20.md` — ⚠️ 所有 26 个账号被 AWS 暂停（历史快照）
- `references/kiro-9router-systemd-pitfalls.md` — 9Router systemd 配置陷阱和修复

---

## 单账号健康检查（新）

> ⚠️ **端点到端验证铁律**：必须走生产链路 — **New API → 9Router 路由 → 代理 → 上游模型**。
> 绝对不能用 `api.openai.com` 直连（免费账号会 429 quota exceeded）。这是浩哥明确纠正过的。

### 快速运行

```bash
# 单账号检查
python3 ~/.hermes/skills/automation/account-registration/scripts/health_check_single.py <email>

# 示例
python3 ~/.hermes/skills/automation/account-registration/scripts/health_check_single.py stephaniejenkins@qhvip.cc
```

### 检查链路

```
OAuth Refresh (auth.openai.com)
    → access_token 更新到 9Router SQLite
    → New API (localhost:3000) + API Key
    → 9Router 路由引擎 (读取 providerConnections)
    → IPRoyal 住宅代理 (geo.iproyal.com:12321)
    → 上游 Codex 模型 (gpt-5.5)
```

### 关键配置

- **New API 端点**: `http://localhost:3000/v1/chat/completions`（不是 9000）
- **New API Key**: token id=1 (`uL6KoYoLALlLfuPnsKtZi91PnjoCjRJZESGYThukUX1EGzyH`)
- **Codex OAuth client_id**: `app_EMoamEEZ73f0CkXaXp7hrann`（来源：9router/src/lib/oauth/constants/oauth.js）
- **OAuth 刷新端点**: `https://auth.openai.com/oauth/token`

详见 `references/health-check-config.md`。

---

## 相关技能

- **llm-api-gateway** — New API 部署和 9Router 上游代理配置，账号最终通过 9Router 提供 API 服务

> **已吸收的技能**（内容已合并到本技能或作为 references/）：
> - `chatgpt-account-sync` — ChatGPT→9Router 同步现已集成在「注册后验证与同步」章节
> - `platform-to-9router-sync` — 多平台同步逻辑和 SQLite schema 已移入 references/
> - `kiro-account-validation` — Kiro 账号验证已合并为「Kiro 账号验证」章节（见下方），脚本和参考资料移入 `scripts/kiro-*.py` 和 `references/kiro-*.md`

## 参考资料

### 通用 / ChatGPT
- `references/git-tracking-9router-data.md` — 🔥 **Git 追踪 9Router 数据变更**：初始化、.gitignore 模板、变更工作流、commit 规范、SQLite WAL 陷阱、回退操作
详见 `references/health-check-config.md`。
- `references/cloudflare-blocking.md` — Cloudflare 封锁问题及缓解措施
- `references/nine-router-sync.md` — 9Router 同步完整流程
- `references/check_valid_debug_2026-05-09_session2.md` — check_valid() 调试记录
- `references/check_valid_debug_2026-05-09.md` — 早期调试记录
- `references/herosms-openai-country-data.md` — 🆕 HeroSMS OpenAI 服务全球号码库存与价格（2026-05-26），含推荐测试策略
- `references/add-phone-cloudflare-block.md` — 🔥 **add-phone/send 返回 400 的真正根因**：Cloudflare JS Challenge 拦截浏览器 fetch API
- `references/sms-provider-landscape.md` — 🔥 SMS 提供商全景：5sim/HeroSMS/SMS-Activate 实测结果、OpenAI 双重验证机制、未测试方案清单
- `references/add-phone-cf-bypass-technique.md` — CF 绕过技术详解
- `references/herosms-api.md` — HeroSMS API 文档
- `references/9router-sqlite-schema.md` — **9Router v0.4.31+ SQLite 表结构**（db.json 已废弃），含 proxyPools、providerConnections 格式和 CRUD 操作
- `references/import-from-external-json.md` — 从外部 JSON 导出文件导入账号（非 any-auto-register 来源），含过期 token 陷阱
- `references/import-tool.md` — Web 上传导入工具：Flask + Nginx 架构，拖拽上传、异步验证、实时结果展示
- `references/herosms-build-phone-callbacks-fix.md` — HeroSMS 配置缺失修复
- `references/chatgpt-sync-diagnostics.md` — ChatGPT 同步诊断方法
- `references/account-selection-loop-2026-05-26.md` — 🔥 account_selection → add_phone 循环（新循环模式，不同于死循环修复）
- `references/force-cancel-stuck-task.md` — 🔥 卡在 cancel_requested 的任务强制清理方法

### Kiro 专项（从 kiro-account-validation 吸收）
- `references/kiro-kiro-api-architecture.md` — ⚠️ Q Chat API vs CodeWhisperer 两个独立 AWS 服务
- `references/kiro-kiro-api-details.md` — AWS OIDC 和 Q API 请求/响应详情
- `references/kiro-kiro-credential-gap.md` — 新注册账号凭证缺失问题
- `references/kiro-kiro-login-quota-behavior.md` — 登录尝试 & freeTrial 服务器端控制
- `references/kiro-kiro-otp-automation.md` — CF Worker 邮箱 API 和 OTP 提取
- `references/kiro-kiro-pricing-policy.md` — Kiro/Amazon Q Developer 定价
- `references/kiro-chat-api-endpoint-discovery.md` — ⚠️ 哪个端点真正验证账号（`generateAssistantResponse` 是唯一权威端点，`/chat` 是假阳性）
- `references/kiro-chat-api-vs-codewhisperer.md` — 两个 API 的区别和陷阱
- `references/kiro-browser-relogin.md` — **Kiro 浏览器重新登录**：Camoufox 代理格式、OIDC 参数、asyncio 隔离、OTP 处理
- `references/kiro-account-status-2026-05-20.md` — 账号状态历史快照
- `references/kiro-9router-import.md` — 验证后导入 9Router SQLite
- `references/kiro-9router-sqlite-import.md` — 9Router SQLite 导入模式
- `references/kiro-9router-sync.md` — Kiro → 9Router 同步指南
- `references/kiro-9router-systemd-pitfalls.md` — 9Router systemd 配置陷阱
- `references/kiro-proxy-config-verification.md` — 代理配置验证
- `references/kiro-proxy-providers.md` — 代理提供商评估
- `references/kiro-data-sources-guide.md` — any-auto-register vs 9Router 数据源差异
- `references/kiro-credential-persistence.md` — 凭证跨会话持久化模式
- `references/kiro-known-pitfalls.md` — Kiro 已知陷阱合集
- `references/kiro-kiro-api-modes.md` — Kiro API 模式详解
- `references/kiro-chatgpt-oauth-client-trap.md` — ChatGPT OAuth client_id 陷阱
- `references/kiro-any-auto-register-db-schema.md` — any-auto-register DB schema
- `references/kiro-account-status-2026-05-12.md` — 早期账号状态快照
- `references/kiro-account-status-2026-05-26.md` — ⚠️ 最新：0/45 可用（25 暂停，20 缺凭证）
- `references/kiro-camoufox-relogin-pitfalls.md` — ⚠️ 浏览器重新登录6大陷阱（screen/代理/issuerUrl/scopes等）

---

## 安全注意事项

- **密码存储**：账号密码明文存储于 `accounts.password`，生产环境需加密
- **API 密钥**：接码平台密钥存在于 `provider_settings.auth_json`，需保护数据库文件
- **会话隔离**：每次注册使用独立浏览器上下文，避免 Cookie 泄露
- **禁用代理时**：确保服务器 IP 不会被目标平台封禁，ChatGPT 对数据中心 IP 敏感
