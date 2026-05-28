# add-phone Cloudflare 绕过调试方法论

> 2026-05-27 · 从发现到修复的完整调试路径

## 排查层序（逐层验证，不跳步）

### L1：代理是否生效？
```bash
# 查任务日志第一行
journalctl -u any-auto-register --no-pager | grep "使用代理"
# 预期：使用代理: http://4GJSsuSsb3vci2UA:***@geo.iproyal.com:12321
```
如果无此行 → `proxy_pool.get_next()` 返回 None。查 `proxies` 表 `is_active=1`。

### L2：API 返回什么？
```bash
# 直接 curl 测试 OpenAI 端点
curl -s --proxy 'http://USER:PASS_country-us@geo.iproyal.com:12321' \
  -X POST 'https://auth.openai.com/api/accounts/add-phone/send' \
  -H 'Content-Type: application/json' \
  -d '{"phone_number":"+1XXXXXXXXXX"}'
```
- 返回 HTML（Cloudflare JS Challenge）→ L3 修复
- 返回 JSON 错误 → 号码被拒，换 SMS 提供商
- 返回 200 → 正常

### L3：浏览器 fetch 被 CF 拦截
浏览器页面能过 CF，但 `page.evaluate("fetch(...)")` 发的独立 XHR 会触发更严格的 CF 保护。

**修复**：用页面交互代替 fetch API：
```python
# 旧：_browser_fetch(page, "/api/accounts/add-phone/send", method="POST", body=...)
# 新：
phone_input = page.locator('input[type="tel"]').first
phone_input.click(click_count=3)
phone_input.type(phone_number, delay=80)
page.keyboard.press("Tab")
page.keyboard.press("Enter")
```

### L4：SPA 同页 OTP 检测
OpenAI 的 add-phone 页是 SPA——提交后 OTP 输入框出现在同一页面，URL 不变。需要检测 OTP 输入框的出现而非等待 URL 跳转：
```python
# 等待 OTP 输入框出现在当前页面
otp_input = _find_otp_input(page)  # 多选择器 fallback
```

### L5：SMS 是否送达
即使页面交互成功、OTP 输入框出现，SMS 也可能不送达。
- HeroSMS：已验证 US (187) 和 CA (36) 均收不到 OpenAI SMS → 整条线不可用
- 需换 5sim、SMSPool、SMS-Activate 等

## 关键提交
- `0dff59d` — 初版 page interaction 替换 fetch API（含 `_fill_and_submit_phone`、`_find_otp_input`）
- `e168ce5` — 改 keyboard Enter + SPA 同页 OTP 检测 + 错误检测 + 页面内容 dump
