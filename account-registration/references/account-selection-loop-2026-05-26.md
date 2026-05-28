# account_selection → add_phone 循环 (2026-05-26 发现)

## 事件链

```
ChatGPT headed 注册 → 成功完成邮箱验证 → about_you → OAuth 开始
→ OpenAI 重定向到 choose-an-account
→ 点击目标账号 → OpenAI **不回调**，重定向到 add-phone（强制手机验证）
→ HeroSMS 租号成功 → 提交手机号到 add-phone/send → **400 失败**
→ 跳过 add-phone → 重访 OAuth auth_url → OpenAI 又送回 choose-an-account
→ 回到开头 → 无限循环
```

## 与 add_phone 死循环的区别

这是**不同的循环**。add_phone 死循环（已修复）的路径是 `OTP↔add_phone`，跳过后 page_type 为空。这个循环的路径是 `account_selection→add_phone→account_selection`，跳过后 page_type 不为空（是 account_selection），不会被之前修复的空 page_type 检测拦截。

## add-phone/send 返回 400 的真正原因

2026-05-27 最终确诊为 **Cloudflare JS Challenge**，不是号码质量问题。详见 `add-phone-cloudflare-block.md`。

## 修复进度

1. ✅ add_phone 死循环（空 page_type）— 已修复并 commit (`b137783`)
2. ❌ account_selection → add_phone 循环 — 等待 CF 修复后验证是否自动解决
3. 🔥 add-phone/send Cloudflare 拦截 — 已确诊，修复方向：页面交互提交替代 fetch API
