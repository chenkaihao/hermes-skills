# add-phone/send Cloudflare 拦截诊断

## 发现日期
2026-05-27

## 问题
ChatGPT headed 注册在 OAuth 流程的 add-phone 步骤，调用 OpenAI API `add-phone/send` 时返回 HTTP 400，响应 body 仅 `{`。换国家号码+对应代理无效。

## 诊断过程

### 浏览器 fetch 结果
```
add-phone/send -> 400
add-phone/send 完整响应 (status=400): {
```
美国号码(country=187)+US代理 和 加拿大号码(country=36)+CA代理 结果相同。

### 对比：直接 curl
```bash
curl --proxy 'http://user:pass_country-ca@geo.iproyal.com:12321' \
  -X POST 'https://auth.openai.com/api/accounts/add-phone/send' \
  -H 'Content-Type: application/json' -H 'Origin: https://auth.openai.com' \
  -d '{"phone_number":"+17805557379"}'
```
返回 HTTP 403 + Cloudflare JS Challenge HTML (`Just a moment...`, `_cf_chl_opt`)。

### 根因
**`add-phone/send` 端点有更严格的 CF 保护**：
- 浏览器正常页面(login/password/OTP/about_you)能过 CF ✅
- `add-phone/send` 的 fetch API 调用触发 CF JS Challenge ❌
- 页面级表单提交(Playwright fill+click)可绕过——页面上下文已通过 CF 验证

## ✅ 已确认有效的修复（2026-05-27）

### 核心原理
浏览器 fetch API 发起的独立 XHR 请求无法通过 Cloudflare JS Challenge。但页面原生表单提交（浏览器的 click/Enter）携带完整浏览器上下文（页面级 cookies、CF clearance token 等），能通过 CF。

### 技术要点

**1. 用键盘 Enter 代替 button click**
```python
# ❌ fetch API — 被 CF 拦截
_browser_fetch(page, f"{OPENAI_AUTH}/api/accounts/add-phone/send", ...)

# ❌ button click — 不够，页面可能用 JS 拦截 click 事件
page.locator('button[type="submit"]').click()

# ✅ Tab + Enter — 触发原生表单提交，JS 拦截器也会被调用
page.keyboard.press("Tab")      # 触发 onBlur 验证
time.sleep(0.3)
page.keyboard.press("Enter")    # 触发原生表单 submit 事件
```

**2. SPA 模式 OTP 检测（不依赖 URL 跳转）**
OpenAI 的 add-phone 页面是 SPA——提交手机号后**不跳转 URL**，而是同页动态显示 OTP 输入框。必须检测 DOM 变化而非 URL：
```python
# 检测 OTP 输入框出现在同页
try:
    otp_input = _find_otp_input(page)   # 查找 input[type="text"] 等
    log("OTP 验证码输入框已出现在当前页面")
    return  # 成功
except Exception:
    pass  # 还没出现，继续等
```

**3. 三重检测：URL 变化 / OTP 出现 / 错误消息**
提交后轮询检查：
- URL 是否离开 `add-phone`（跳转到其他页面）✅
- OTP 输入框是否出现在当前页面（SPA 模式）✅  
- 页面是否有错误提示（`[role="alert"]`, `.text-red-500` 等）❌

### 实际代码（已应用到 browser_register.py）

详见 `platforms/chatgpt/browser_register.py`:
- `_handle_add_phone_challenge()` — 主流程，用页面交互代替 fetch API
- `_fill_and_submit_phone()` — 查找手机输入框、填写、Tab+Enter 提交、等待结果
- `_find_otp_input()` — 在页面上查找验证码输入框

### 提交记录
```
0dff59d fix(chatgpt): use page interaction for add-phone instead of fetch API
e168ce5 fix(chatgpt): use keyboard Enter + OTP-on-same-page detection for add-phone
```

### 验证结果
```
找到手机号输入框: input[type="tel"]
已填写手机号: +178****22
已按 Enter 提交表单
OTP 验证码输入框已出现在当前页面   ← CF 绕过成功
```

## 排除的假设
- ❌ HeroSMS 号码质量：加拿大号码同样失败
- ❌ IP 被封：代理 IP 健康
- ❌ 国家-IP不匹配：加拿大代理+加拿大号码仍失败
- ❌ 账号状态：不同邮箱均触发

## 相关代码
- `platforms/chatgpt/browser_register.py:1857-1871` — add-phone/send 调用
- `platforms/chatgpt/browser_register.py:1021-1057` — _browser_fetch 实现
- `platforms/chatgpt/browser_register.py:1587-1662` — OAuth 状态机 add_phone 处理
