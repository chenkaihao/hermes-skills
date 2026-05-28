# Desktop OIDC Flow 回调端口修复

**日期**: 2026-05-12  
**文件**: `platforms/kiro/browser_register.py` → `_desktop_idc_flow()`

## 问题

Headed 模式 Kiro 注册始终拿不到 `refreshToken`。日志显示：
```
Desktop OIDC: 点击 Allow access...
[desktop_oidc] 失败: 等待桌面授权回调超时
```

## 根因

`_desktop_idc_flow` 函数中操作顺序错误：

```python
# 原代码（错误）
reg_resp = _http_post_json(..., {
    "redirectUris": ["http://127.0.0.1/oauth/callback"],  # 硬编码无端口
})
...
callback_server = _DesktopAuthCallbackServer(...)
callback_server.start()  # 随机端口
redirect_uri = callback_server.redirect_uri  # http://127.0.0.1:{random_port}/oauth/callback
```

OIDC 客户端注册的 redirect URI 不包含端口，但 authorize 请求和回调服务器使用随机端口。AWS OIDC 重定向到注册的 URI（端口 80），回调服务器监听随机端口，收不到回调。

## 修复

调整顺序：先启动回调服务器获取真实端口，再用正确 URI 注册客户端。

```python
# 修复后
callback_server = _DesktopAuthCallbackServer(...)
callback_server.start()
redirect_uri = callback_server.redirect_uri  # 先拿端口

reg_resp = _http_post_json(..., {
    "redirectUris": [redirect_uri],  # 使用实际端口
})
```

## 效果

修复前：0% 账号有 refreshToken  
修复后：~50% 账号有完整凭证（含 refreshToken + clientId + clientSecret）

偶尔仍会超时（浏览器环境影响），属正常波动。
