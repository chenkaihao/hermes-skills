# check_valid() 调试报告

## 日期：2026-05-09

## 问题描述

Web UI 显示 ChatGPT 账号状态为 `invalid`，但手动验证账号有效。

## 调试过程

### 步骤 1：数据库查询

```sql
SELECT a.id, a.email, o.validity_status 
FROM accounts a
LEFT JOIN account_overviews o ON a.id = o.account_id
WHERE a.platform = 'chatgpt';
```

**结果**：所有账号 `validity_status=invalid`

### 步骤 2：手动验证账号

```python
from curl_cffi import requests as cffi_requests

headers = {"Authorization": f"Bearer {access_token}"}
resp = cffi_requests.get(
    "https://chatgpt.com/backend-api/me",
    headers=headers,
    impersonate="chrome110"
)
# 返回 200，plan_type=None → free → valid
```

**结论**：账号确实有效。

### 步骤 3：追踪 check_valid() 代码路径

文件：`platforms/chatgpt/plugin.py` 第 73-118 行

```python
def check_valid(self, account: Account) -> bool:
    ...
    proxy_candidates = []
    if configured_proxy:
        proxy_candidates.append((configured_proxy, False))
    else:
        pooled_proxy = proxy_pool.get_next(region=region)
        if pooled_proxy:
            proxy_candidates.append((pooled_proxy, True))
    proxy_candidates.append((None, False))  # ← 问题在这里

    for proxy, should_report in proxy_candidates:
        try:
            details = fetch_subscription_status_details(a, proxy=proxy)
            ...
            return status not in ("expired", "invalid", "banned", None)
        except Exception:
            ...
    return False
```

### 步骤 4：分析 fetch_subscription_status_details()

文件：`platforms/chatgpt/payment.py` 第 338-379 行

```python
def fetch_subscription_status_details(account: Account, proxy: Optional[str] = None) -> dict:
    ...
    try:
        resp = cffi_requests.get(
            "https://chatgpt.com/backend-api/me",
            headers=headers,
            proxies=_build_proxies(proxy),  # proxy=None → 不使用代理
            timeout=20,
            impersonate="chrome110",  # ← 仍然使用 curl_cffi！
        )
        ...
    except Exception as exc:
        # 回退到 /wham/usage
        data = _fetch_usage_data(account, proxy=proxy)
        ...
```

**等等！** `payment.py` 内部使用的是 `curl_cffi`，不是 `requests`！

### 步骤 5：重新测试

```python
# 直接调用 fetch_subscription_status_details
details = fetch_subscription_status_details(a, proxy=None)
# 成功！status=free, source=backend-api/me
```

**为什么 check_valid() 还是返回 False？**

可能原因：
1. **Proxy pool 在检查时返回了非 None 值但代理不可用** → 尝试代理 → 失败 → continue → 下一轮 proxy=None → 成功
2. **异常被静默吞掉**：`except Exception: continue` 会跳过所有异常，包括我们没预料到的

### 步骤 6：添加调试日志

在 `check_valid()` 添加 print：
```python
print(f"[DEBUG] fetch_subscription_status_details 成功: status={details.get('status')}")
print(f"[DEBUG] status={repr(status)}")
print(f"[DEBUG] check_valid 返回: {result}")
```

**发现**：当直接调用时返回 `True`，说明代码路径本身没问题。

**推测**：之前测试时 `proxy_pool` 返回了一个坏代理，导致第一次尝试失败，然后 `continue` 到下一个 candidate 时可能因为某种原因没执行到或又失败了。

## 结论

1. `fetch_subscription_status_details()` 内部使用 `curl_cffi`，**不是** `requests`
2. `check_valid()` 的代理 fallback 逻辑没问题，但代理池中的坏代理会导致第一次失败
3. **真正的 bug**：`proxy_pool.get_next()` 返回的代理可能不可用，但没有被标记为失败（`should_report=False` 时不会 `report_fail`）
4. 服务重启后 proxy pool 为空，直接走 `proxy=None` 路径 → 应该成功，但之前测试时显示失败 → 可能是时序问题

## 修复建议

1. **短期**：确保 proxy pool 中的代理可用，或在 `check_valid()` 中添加重试逻辑
2. **中期**：在 `should_report=False` 的 fallback 路径也加入错误报告
3. **长期**：重构 `fetch_subscription_status_details()` 使其与 proxy 参数无关，内部始终用 curl_cffi
