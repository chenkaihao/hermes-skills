# Kiro 新注册账号凭证缺失问题

**发现时间**: 2026-05-12 (批量注册脚本测试)

## 现象

通过 any-auto-register API 注册的 Kiro 账号，`account_credentials` 表只有 `accessToken` + `legacy_token`，缺失 `refreshToken` / `clientId` / `clientSecret`。

## 根因

any-auto-register Kiro 注册流程未执行 device auth 步骤（`step12f_device_auth`），导致无法获取 OAuth client credentials。

## 影响

- 三步验证 Token 刷新步骤无法执行
- 降级：直接用 accessToken 查询（`_fetch_usage(accessToken)`）
- 9Router 同步无法获取完整凭证

## 当前降级方案

```python
# validate_kiro_account 中的降级逻辑
if rt and cid and csec:
    access_token = refresh_kiro_token(rt, cid, csec)["accessToken"]
elif at:
    access_token = at  # 降级
else:
    return {"stage": "no_credentials"}
```
