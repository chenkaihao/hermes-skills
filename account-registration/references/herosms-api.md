# HeroSMS 平台参考

## API 端点

```
https://hero-sms.com/stubs/handler_api.php
```

### 余额查询
```
GET ?action=getBalance&api_key=YOUR_KEY
→ ACCESS_BALANCE:13
```

### 国家列表
```
GET ?action=getCountries
→ [{id, rus, eng, chn, visible, retry, rent, multiService}]
```

### 租用号码
```
GET ?action=getNumberV2&service=dr&country=187&api_key=YOUR_KEY
→ {activationId, phoneNumber, countryPhoneCode, activationCost}
```

### 查收短信
轮询：`GET ?action=getSmsCode&activationId=XXX&api_key=XXX`
完成：`GET ?action=finishSms&activationId=XXX&api_key=XXX`

---

## 国家代码（可见物理号）

| ID | 英文 | 中文 | visible |
|----|------|------|---------|
| 187 | USA | 美国（物理） | 1 |
| 12  | USA (virtual) | 美国（虚拟） | 0 |
| 16  | United Kingdom | 英格兰 | 1 |
| 3   | China | 中国 | 1 |

> ⚠️ 虚拟号通常无库存，注册平台需选择 visible=1 的物理号

---

## 注册服务代码

| 平台 | service 参数 |
|------|-------------|
| ChatGPT / Codex | `dr` |

---

## 定价参考

美国物理号（ID=187）：
- ChatGPT 注册：~0.495 元/次
- 短信接收：通常包含在激活成本内
