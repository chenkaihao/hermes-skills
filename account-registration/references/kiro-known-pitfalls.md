# 11. CodeWhisperer 403 ≠ 账号不可用 — 三步验证的第三步误判

**发现日期**: 2026-05-12 (第二次验证)

**问题**: `ListAvailableModels` API 返回 `403 AccessDeniedException: "temporarily is suspended"` 会让三步验证判定账号"无效"。但实际上这个 403 只影响 CodeWhisperer 权限，**不影响聊天 API**。

**证据**: 
- 家庭代理 + IPRoyal 测试 → 23/23 账号 CodeWhisperer 第三步全部 403
- 同一批账号用聊天 API (`q.us-east-1.amazonaws.com/chat`) 测试 → 23/23 全部通过
- 9Router 旧测试（发 "Hi" 走聊天路由）→ 22/22 全部通过

**结论**: CodeWhisperer 的限制不等于账号不可用。对于通过 9Router 路由的实际聊天请求，这些账号完全正常。

**当前脚本行为**: `check_kiro_accounts.py` 把 CodeWhisperer 403 当致命错误 → 标记账号 invalid。这是**过度严格**的判断。

**修复方向**:
```python
# 区分 CodeWhisperer 403 和真正的凭证失效
if "temporarily is suspended" in error_msg:
    result["valid"] = True  # 聊天 API 可用，只是 CodeWhisperer 受限
    result["stage"] = "codewhisperer_blocked"
    result["warning"] = "CodeWhisperer blocked, chat API still functional"
```

## 12. 聊天 API 才是权威验证标准

**发现日期**: 2026-05-12

**正确测试方法**:
```python
# 直接调 Kiro 聊天 API
r = cffi_requests.post(
    "https://q.us-east-1.amazonaws.com/chat",
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "aws-sdk-js/1.0.18",
    },
    json={
        "messages": [{"role": "user", "content": "Hi"}],
        "maxTokens": 50,
    },
    proxies=proxy,
    impersonate="chrome131",
    timeout=30
)
# HTTP 200 = 账号可用，不管 CodeWhisperer 返回什么
```

**9Router 的健康检查**: 9Router 的 Kiro 连接测试调用 `codewhisperer.us-east-1.amazonaws.com` ListAvailableModels，所以即使聊天可用，9Router 也会标记 unavailable。但实际聊天路由走 `q.us-east-1.amazonaws.com`，功能不受影响。

## 13. accessToken-only 账号的假阳性

**问题**: `check_kiro_accounts.py` 对没有 refreshToken 的账号跳过实际 API 测试，只要存在 accessToken 就标记 valid。这产生假阳性。

**影响**: 
- 2026-05-12 报告显示 14 个 "valid" Kiro 账号，全部是 accessToken-only
- 推送到 9Router 后全部 403（因为 9Router 需要 refreshToken）
- 给用户造成"有可用账号"的假象

**修复**: 
1. 区分 "valid" 和 "has_credentials_only" 两种状态
2. accessToken-only 账号不应标为 valid，应标为 "token_exists_untested"
3. 在报告中明确标注哪些账号经过了实际 API 测试
