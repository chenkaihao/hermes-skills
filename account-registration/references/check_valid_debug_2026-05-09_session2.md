# check_valid() 完整调试报告 (2026-05-09 会话)

## 问题现象

- Web UI 显示所有 ChatGPT 账号状态为 `invalid`
- 用户询问账号是否真的无效，要求用 token 测试

## 调试过程

### 1. 初步验证（脚本方式）

```python
import sqlite3
from curl_cffi import requests as cffi_requests

conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
cursor = conn.cursor()
cursor.execute("SELECT value FROM account_credentials WHERE account_id = 34 AND key = 'access_token'")
access_token = cursor.fetchone()[0]

headers = {"Authorization": f"Bearer {access_token}"}

resp = cffi_requests.get(
    "https://chatgpt.com/backend-api/me",
    headers=headers,
    timeout=20,
    impersonate="chrome110"  # 必须伪造浏览器指纹
)
# 状态码: 200
# plan_type: None → free 账号
```

**结论**：账号确实有效，`curl_cffi + impersonate="chrome110"` 可以成功。

### 2. 使用 requests 库对比测试

```python
import requests

resp = requests.get("https://chatgpt.com/backend-api/me", headers=headers)
# 状态码: 403 → Cloudflare 拦截
```

**结论**：`requests` 库无法使用，必须用 `curl_cffi`。

### 3. 直接调用 check_valid()（独立脚本）

构建完整 `PlatformAccount` 对象后调用：

```python
from core.platform_accounts import build_platform_account
from core.registry import load_all, registry_module
from core.base_platform import RegisterConfig

load_all()
with Session(engine) as session:
    model = session.get(AccountModel, 34)
    account_obj = build_platform_account(session, model)
    plugin = registry_module._registry['chatgpt'](config=RegisterConfig())
    result = plugin.check_valid(account_obj)
    # → True ✅
```

**结果**：`check_valid()` 返回 `True`，但 `get_last_check_overview()` 返回的 `plan` 为 `free`。

**发现**：代码本身逻辑正确，`fetch_subscription_status_details()` 使用 `curl_cffi` 成功。

### 4. 通过 API 触发检查任务

```python
resp = requests.post("http://localhost:8000/api/accounts/34/check")
task_id = resp.json()["id"]
# 监控任务 → 状态 succeeded，日志显示 "peterl@qhvip.cc: 有效"
```

**结果**：通过 API 调用后，数据库 `validity_status` 更新为 `valid`。

### 5. 批量验证所有账号

```bash
/usr/bin/python3.12 << 'EOF'
import sqlite3
from curl_cffi import requests as cffi_requests

conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
cursor = conn.cursor()
cursor.execute("SELECT a.id, a.email, ac1.value FROM accounts a LEFT JOIN account_credentials ac1 ON ... WHERE a.platform='chatgpt'")

for id_, email, token in rows:
    resp = cffi_requests.get("https://chatgpt.com/backend-api/me", headers={"Authorization": f"Bearer {token}"}, impersonate="chrome110")
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ {email}: plan_type={data.get('plan_type')}")
    else:
        print(f"❌ {email}: {resp.status_code}")
EOF
```

**结果**：所有 7 个账号均返回 200，`plan_type=None` → free。

## 关键发现

### fetch_subscription_status_details 内部实现

文件：`platforms/chatgpt/payment.py:338-379`

```python
def fetch_subscription_status_details(account: Account, proxy=None) -> dict:
    headers = {"Authorization": f"Bearer {account.access_token}"}
    try:
        resp = cffi_requests.get(
            "https://chatgpt.com/backend-api/me",
            headers=headers,
            proxies={"http": proxy, "https": proxy} if proxy else None,
            timeout=20,
            impersonate="chrome110",  # ← 关键：内部使用 curl_cffi
        )
        resp.raise_for_status()
        return {"status": _subscription_status_from_me(resp.json()), "source": "backend-api/me"}
    except:
        # 回退到 /wham/usage（同样用 curl_cffi）
        data = _fetch_usage_data(account, proxy=proxy)
        return {"status": _subscription_status_from_usage(data), "source": "backend-api/wham/usage"}
```

**注意**：`proxy=None` 时，`_build_proxies(proxy)` 返回 `None` → `cffi_requests.get(..., proxies=None)` → **不使用代理**，但仍用 `curl_cffi` → **应成功**。

### check_valid() 的代理选择逻辑

```python
proxy_candidates = []
if configured_proxy:
    proxy_candidates.append((configured_proxy, False))
else:
    pooled_proxy = proxy_pool.get_next(region=region)
    if pooled_proxy:
        proxy_candidates.append((pooled_proxy, True))
proxy_candidates.append((None, False))  # ← fallback 到无代理

for proxy, should_report in proxy_candidates:
    try:
        details = fetch_subscription_status_details(a, proxy=proxy)
        ...
        return status not in ("expired", "invalid", "banned", None)
    except Exception:
        continue  # ← 静默吞掉所有异常
return False
```

**流程**：
1. 有配置代理 → 先试配置代理
2. 无配置代理 → 从代理池取（可能返回 None）
3. 最后 fallback 到 `proxy=None`（不使用代理，仅用 curl_cffi）

**预期**：如果前两次失败，第 3 次 `proxy=None` 应成功（因为 curl_cffi 不需要代理）。

**实际现象**：`check_valid()` 返回 `False`，说明整个循环内所有尝试都抛出了异常。

**可能的真实原因**：
- `fetch_subscription_status_details()` 内部 `cffi_requests.get()` 仍然失败（网络问题、DNS、TLS 等）
- `account.extra` 中缺少 `access_token` → `account.access_token` 为空 → `ValueError("账号缺少 access_token")`
- `_fetch_usage_data()` 也失败 → 两次都抛异常 → `continue` 循环结束 → `return False`

### 为什么直接测试成功而 lifecycle 检查失败？

可能原因：
1. **Account 对象构建差异**：生命周期管理器中构建的 `PlatformAccount` 对象可能缺少 `extra` 字段或字段值不同
2. **时序问题**：注册后立刻检查，`access_token` 可能还未写入 `account_credentials`（虽然测试中发现已写入）
3. **网络抖动**：测试时网络正常，检查时网络短暂中断

## 修复建议优先级

### P0: 立即修复（不影响功能但误导用户）

在 `check_valid()` 中添加详细日志，捕获并记录异常信息：

```python
for proxy, should_report in proxy_candidates:
    try:
        details = fetch_subscription_status_details(a, proxy=proxy)
        ...
    except Exception as exc:
        logging.warning(f"check_valid 失败 (proxy={proxy}): {exc}")
        if should_report and proxy:
            proxy_pool.report_fail(proxy)
        continue
```

### P1: 短期修复（确保准确性）

确保 fallback 路径（`proxy=None`）也成功：

```python
# 如果所有带代理的尝试都失败，再试一次无代理并强制使用 curl_cffi
for proxy, should_report in proxy_candidates:
    if proxy is None:
        continue  # 最后再试无代理
    try:
        ...
    except:
        ...

# 最后 fallback：无代理 + curl_cffi
try:
    details = fetch_subscription_status_details(a, proxy=None)
    ...
    return status not in (...)
except Exception as exc:
    logging.error(f"check_valid 最终 fallback 失败: {exc}")
    return False
```

### P2: 长期重构

1. 将 `fetch_subscription_status_details()` 中的 `proxy` 参数移除或改为可选，内部始终使用 `curl_cffi`
2. 代理参数仅用于 `cffi_requests.get(..., proxies=...)`，不影响 `impersonate` 参数
3. 确保 `account.extra` 的 `access_token` 写入时机与账号注册完成时机一致

## 验证结果

| 检查方式 | 结果 | 备注 |
|----------|------|------|
| Web UI | ❌ invalid | 受 bug 影响，显示错误 |
| API 检查任务 | ✅ valid | 修复后（或运气好时）成功 |
| 手动 curl_cffi | ✅ valid | 绕过 bug，直接验证成功 |
| check_valid() 直接调用 | ✅ True | account.extra 完整时成功 |
| check_valid() lifecycle 调用 | ❌ False | bug 复现 |

## 当前账号状态（2026-05-09 15:00 UTC）

| ID | 邮箱 | Web 显示 | 实际状态 |
|----|------|----------|----------|
| 16 | mma@qhvip.cc | invalid | ✅ valid (free) |
| 17 | raymondprice2022@qhvip.cc | invalid | ✅ valid (free) |
| 18 | nicolecampbell@qhvip.cc | invalid | ✅ valid (free) |
| 19 | larrycox99@qhvip.cc | invalid | ✅ valid (free) |
| 20 | sarahkim@qhvip.cc | invalid | ✅ valid (free) |
| 21 | georgehall@qhvip.cc | invalid | ✅ valid (free) |
| 34 | peterl@qhvip.cc | invalid | ✅ valid (free) |
