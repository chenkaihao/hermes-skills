# HeroSMS `build_phone_callbacks` 配置缺失修复

**日期**：2026-05-21  
**症状**：ChatGPT 注册遇到 add_phone 时，`_handle_add_phone_challenge` 抛出 `HeroSMS 未配置 API Key`，但数据库 `provider_settings` 表中 herosms 的 `auth_json` 已正确配置 `herosms_api_key`。

**根因**：`core/registration/helpers.py:build_phone_callbacks()` 第 97 行：

```python
merged = settings_repo.resolve_runtime_settings("sms", provider_key, extra) if definition else dict(extra)
```

HeroSMS 在 `provider_definitions` 表中**没有定义记录**（`definition is None`），导致走 `dict(extra)` 分支。`extra` 来自任务创建时的 API 参数：

```json
{"mail_provider": "cfworker_admin_api", "sms_provider": "herosms", "identity_provider": "mailbox"}
```

其中不包含 `herosms_api_key`，所以 `create_sms_provider` 收不到 API Key。

**修复**：移除 `if definition else dict(extra)` 条件，始终调用 `resolve_runtime_settings` 从 DB 合并配置：

```python
# 修复前
merged = settings_repo.resolve_runtime_settings("sms", provider_key, extra) if definition else dict(extra)

# 修复后
merged = settings_repo.resolve_runtime_settings("sms", provider_key, extra)
```

`resolve_runtime_settings` 本身会从 `provider_settings` 表读取 `config_json` 和 `auth_json` 并合并，无论是否有 definition。修复后 `merged` 正确包含 `herosms_api_key`。

**验证**：
```python
from infrastructure.provider_settings_repository import ProviderSettingsRepository
from core.base_sms import create_phone_callbacks

repo = ProviderSettingsRepository()
provider_key = repo.get_default_provider_key("sms")  # "herosms"
merged = repo.resolve_runtime_settings("sms", provider_key, {})
# merged 应包含: {"sms_country": "187", "herosms_api_key": "48A4de..."}

result = create_phone_callbacks(provider_key, merged, service="chatgpt", country="187")
# result 应为 (PhoneCallbackController, cleanup) 而非 (None, None)
```

**相关文件**：`/root/src/any-auto-register/core/registration/helpers.py` 第 94-97 行

## 补充：HeroSMS 服务名配置

**症状**：修复上述 API Key 问题后，注册仍卡在 `phone-otp/resend` 循环。HeroSMS 能租到号码但永远收不到 OpenAI 发的短信。

**根因**：`HERO_SMS_DEFAULT_SERVICE = "dr"`（DoorDash），而 ChatGPT/OpenAI 的 HeroSMS 服务码是 `"oi"`。`HeroSmsProvider.get_number()` 优先使用 `self.default_service`（非空时不 fallback 到 `service` 参数），导致用错误的服务码租号——租到的号码不会接收 OpenAI 短信。

**修复**：在 `provider_settings` 的 `config_json` 中添加 `"sms_service": "oi"`：

```sql
UPDATE provider_settings 
SET config_json = json_set(config_json, '$.sms_service', 'oi') 
WHERE provider_key = 'herosms';
```

**验证**：HeroSMS API `getActiveActivations` 返回 `service: oi` 即修复生效。修复后成功完成首次完整 OAuth + SMS 注册（roberts@qhvip.cc，2026-05-21）。

**注意**：虚拟号收 OpenAI 验证码成功率约 **20%**。大部分注册仍会因 SMS 未到达而失败。如需提高成功率，考虑更换接码平台。
