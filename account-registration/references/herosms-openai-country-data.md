# HeroSMS OpenAI (service=oi) 号码库存与价格

> 数据获取时间：2026-05-26  
> API Key：`48A4de1A4041b75A6dbe57417A6dc343`（余额 $8.835）  
> 端点：`GET hero-sms.com/stubs/handler_api.php?api_key=KEY&action=getPrices&service=oi`

## 当前配置

- 默认国家：187 (United States)
- 默认服务：oi (OpenAI)
- 当前代理：IPRoyal US (`_country-us`)

## OpenAI 号码库存排行（Top 15）

| 国家 | ID | 库存 | 物理号 | 单价 | 备注 |
|------|-----|------|--------|------|------|
| 🇧🇷 Brazil | 73 | 1,280,409 | 11,760 | $0.050 | 库存最大 |
| 🇺🇸 USA | 187 | 586,907 | 774 | $0.150 | 当前使用，400 被拒 |
| 🇬🇧 United Kingdom | 16 | 260,914 | 15,799 | $0.035 | **物理号最多，低价** |
| 🇨🇦 Canada | 36 | 159,904 | 536 | $0.015 | **最便宜** |
| 🇮🇩 Indonesia | 6 | 110,068 | 33,073 | $0.025 | 物理号库存大 |
| 🇮🇹 Italy | 86 | 99,894 | 2,786 | $0.696 | 贵 |
| 🇦🇹 Austria | 50 | 42,592 | 5,591 | $0.200 | — |
| 🇨🇴 Colombia | 33 | 36,250 | 8,926 | $0.018 | 便宜 |
| 🇦🇺 Australia | 175 | 35,339 | 3,416 | $0.175 | — |
| 🇵🇱 Poland | 15 | 32,134 | 1,551 | $0.450 | — |
| 🇸🇿 Swaziland | 106 | 25,414 | 0 | $0.267 | — |
| 🇻🇪 Venezuela | 70 | 24,724 | 0 | $0.200 | — |
| 🇭🇰 Hong Kong | 14 | 24,225 | 4,362 | $0.050 | — |
| 🇫🇷 France | 78 | 19,698 | 185 | $0.750 | 贵 |
| 🇵🇭 Philippines | 4 | 16,100 | 9,344 | $0.020 | — |

## 推荐测试方向

| 优先级 | 国家 | 理由 | IPRoyal 后缀 | 策略 |
|--------|------|------|-------------|------|
| 🥇 | 🇨🇦 Canada | 最便宜 $0.015，库存充足 | `_country-ca` | 低成本快速试错 |
| 🥈 | 🇬🇧 UK | 物理号最多（15,799），$0.035 | `_country-gb` | 物理号被识破概率低 |
| 🥉 | 🇺🇸 US physical | 774 个物理号（非虚拟号） | `_country-us` | 尝试物理号而非虚拟号 |
| 备选 | 🇮🇩 Indonesia | 33,073 物理号，$0.025 | 需验证 | 物理号量巨大 |

## 关键约束

- **国家-IP 一致性**：OpenAI 可能校验手机号国家 vs 请求 IP 国家。切换国家号码必须同步切换 IPRoyal 代理国家（改 `_country-XX` 后缀）
- **物理号 vs 虚拟号**：`physicalCount` > 0 的国家提供物理号，被 OpenAI 识别为虚拟号的概率更低
- **价格跨度**：$0.015（加拿大）～ $0.900（西班牙），合理控制在 $0.05 以下

## API 用法

```python
import requests, json

API_KEY = "48A4de1A4041b75A6dbe57417A6dc343"

# 余额
balance = requests.get(f"https://hero-sms.com/stubs/handler_api.php?api_key={API_KEY}&action=getBalance").text

# 所有国家 OpenAI 号码价格和库存
prices = requests.get(
    f"https://hero-sms.com/stubs/handler_api.php?api_key={API_KEY}&action=getPrices&service=oi"
).json()

# 国家名映射
countries = requests.get(
    f"https://hero-sms.com/stubs/handler_api.php?api_key={API_KEY}&action=getCountries"
).json()
```

## 配置更新方法

在 any-auto-register 的 `provider_settings` 表中修改 `config_json.sms_country`：

```sql
-- 例如：切换到英国
UPDATE provider_settings 
SET config_json = json_set(config_json, '$.sms_country', '16')
WHERE provider_type = 'sms' AND provider_key = 'herosms';
```

同时确保 IPRoyal 代理后缀匹配：改 `.env` 或 9Router systemd 环境变量中的 `_country-us` → `_country-gb`。
