# Kiro / AWS Builder ID API 详解

## 1. OIDC Token 刷新

**Endpoint**: `https://oidc.us-east-1.amazonaws.com/token`

**Method**: `POST`

**Headers**:
```
Content-Type: application/json
User-Agent: aws-sdk-rust/1.3.9 os/macOS lang/rust
```

**Request Body**:
```json
{
  "grantType": "refresh_token",
  "clientId": "<OAuth 客户端 ID>",
  "clientSecret": "<OAuth 客户端密钥（JWT）>",
  "refreshToken": "<Refresh Token>"
}
```

**Response** (200 OK):
```json
{
  "accessToken": "aoaAAAAAGn68pAYLkkxz13CUXS8SbFl9gIS70RDx5HzoCd793h...",
  "refreshToken": "aorAAAAAGprYH4zSgfCggQvjrfe7Aq2H87IeszQm-DKljmtg8w...",
  "expiresIn": 3600
}
```

**字段说明**:
- `accessToken`: 短期令牌，用于调用 AWS Q API，有效期约 1 小时
- `refreshToken`: 长期刷新令牌，可重复使用，每次刷新可能返回新值
- `expiresIn`: `accessToken` 有效期（秒），通常为 3600

**错误响应**:
- `400 Bad Request`: 参数错误或 clientSecret 格式错误
- `401 Unauthorized`: refreshToken 过期或 clientId/clientSecret 不匹配
- `429 Too Many Requests`: 请求过于频繁，需等待

**注意**:
- `clientSecret` 是 RSA 私钥的 JWT 格式（以 `eyJraW...` 开头），不是明文密码
- `clientId` 是 AWS Builder ID 的 OAuth 应用标识（如 `ntutKACwXU-rf5ihAJatNHVzLWVhc3QtMQ`）
- `refreshToken` 格式为 `aorAAAAAG...`（约 200 字符）

## 2. AWS Q 使用量查询

**Endpoint**: `https://q.us-east-1.amazonaws.com/getUsageLimits`

**Method**: `GET`

**Query Parameters**:
```
?origin=AI_EDITOR&resourceType=AGENTIC_REQUEST&isEmailRequired=true
```

**Headers**:
```
Accept: application/json
Authorization: Bearer <accessToken>
User-Agent: aws-sdk-js/1.0.18 ua/2.1 os/windows lang/js md/nodejs#20.16.0 api/codewhispererstreaming#1.0.18 m/E KiroIDE-0.6.18
x-amz-user-agent: aws-sdk-js/1.0.18 ua/2.1 os/windows lang/js md/nodejs#20.16.0 api/codewhispererstreaming#1.0.18 m/E KiroIDE-0.6.18
```

**响应结构**:
```json
{
  "usageBreakdownList": [
    {
      "resourceType": "CREDIT",
      "usageLimitWithPrecision": 550.0,
      "currentUsageWithPrecision": 0.0,
      "nextDateReset": "2026-06-01T00:00:00Z",
      "freeTrialInfo": {
        "freeTrialStatus": "ACTIVE",
        "usageLimitWithPrecision": 50.0,
        "currentUsageWithPrecision": 0.0,
        "freeTrialExpiry": "2026-05-31T23:59:59Z"
      },
      "bonuses": [
        {
          "displayName": "Bonus Credits",
          "usageLimitWithPrecision": 100.0,
          "currentUsageWithPrecision": 0.0,
          "expiresAt": "2026-05-20T00:00:00Z"
        }
      ]
    }
  ],
  "subscriptionInfo": {
    "subscriptionTitle": "PRO"
  }
}
```

**字段说明**:
- `resourceType`: 资源类型，固定为 `"CREDIT"` 表示使用额度
- `usageLimitWithPrecision`: 基础额度上限（浮点数，表示点数）
- `currentUsageWithPrecision`: 已使用额度
- `nextDateReset`: 下次重置时间（ISO 8601 格式）
- `freeTrialInfo`: 免费试用信息（如有）
  - `freeTrialStatus`: 状态，`"ACTIVE"` 表示有效
  - `usageLimitWithPrecision`: 试用额度上限
  - `currentUsageWithPrecision`: 已使用试用额度
  - `freeTrialExpiry`: 试用到期时间
- `bonuses`: 额外奖励额度列表
  - `displayName`: 奖励名称
  - `usageLimitWithPrecision`: 奖励额度上限
  - `currentUsageWithPrecision`: 已使用奖励额度
  - `expiresAt`: 奖励到期时间
- `subscriptionInfo.subscriptionTitle`: 订阅计划名称（如 `"FREE"`, `"PRO"`, `"PRO_PLUS"`, `"POWER"`）

**EU 备用节点**: 如果 US 节点返回 403，尝试:
```
https://q.eu-central-1.amazonaws.com/getUsageLimits?origin=AI_EDITOR&resourceType=AGENTIC_REQUEST&isEmailRequired=true
```

## 3. 计算总可用额度

```python
base_limit = credit_entry["usageLimitWithPrecision"]
base_current = credit_entry["currentUsageWithPrecision"]
free_trial_limit = free_trial_data["limit"] if free_trial_data else 0
free_trial_current = free_trial_data["current"] if free_trial_data else 0
bonuses_limit = sum(b["limit"] for b in bonuses)
bonuses_current = sum(b["current"] for b in bonuses)

total_limit = base_limit + free_trial_limit + bonuses_limit
total_current = base_current + free_trial_current + bonuses_current
percent_used = round(total_current / total_limit * 100, 1) if total_limit > 0 else 0
```

## 4. AI 服务验证：ListAvailableModels API

**Endpoint**: `https://codewhisperer.us-east-1.amazonaws.com`

**Method**: `POST`

**Headers**:
```
Content-Type: application/x-amz-json-1.0
x-amz-target: AmazonCodeWhispererService.ListAvailableModels
Authorization: Bearer <accessToken>
Accept: application/json
User-Agent: aws-sdk-js/1.0.18 ua/2.1 os/windows lang/js md/nodejs#20.16.0 api/codewhispererstreaming#1.0.18 m/E KiroIDE-0.6.18
x-amz-user-agent: aws-sdk-js/1.0.18 ua/2.1 os/windows lang/js md/nodejs#20.16.0 api/codewhispererstreaming#1.0.18 m/E KiroIDE-0.6.18
```

**Request Body** (minimal — no `profileArn` needed):
```json
{
  "origin": "AI_EDITOR"
}
```

**关键发现** (2026-05-12):
- `profileArn` 字段是**可选的**，省略它返回 HTTP 200
- 如果传入 `profileArn`（如 `arn:aws:codewhisperer:us-east-1:699475941385:profile/EHGA3GRVQMUK`），API 返回 400 `ValidationException`
- 不传 `profileArn` 或传空字符串，返回 200 并包含模型列表

**Success Response** (200 OK):
```json
{
  "defaultModel": {
    "modelId": "auto",
    "modelName": "Auto",
    "rateMultiplier": 1.0,
    "rateUnit": "Credit",
    "supportedInputTypes": ["TEXT", "IMAGE"],
    "tokenLimits": { "maxInputTokens": 1000000, "maxOutputTokens": 64000 }
  },
  "models": [
    {
      "modelId": "claude-sonnet-4.5",
      "modelName": "Claude Sonnet 4.5",
      "description": "The Claude Sonnet 4.5 model",
      "rateMultiplier": 1.0,
      "rateUnit": "Credit",
      "tokenLimits": { "maxInputTokens": 200000, "maxOutputTokens": 64000 }
    },
    ...
  ]
}
```

**字段说明**:
- `defaultModel`: 系统默认模型（通常是 `"auto"`）
- `models`: 可用模型列表，每个包含 `modelId`, `modelName`, `description`, `rateMultiplier`, `tokenLimits`
- `rateMultiplier`: 费率倍率，1.0 表示标准费用
- `tokenLimits`: 输入/输出 token 限制

**错误响应**:
- `400 ValidationException`: 请求格式错误或 `profileArn` 无效
- `403 AccessDeniedException`: token 无效或账号被暂停
  - 错误信息：`"Your User ID (<UUID>) temporarily is suspended. We've locked your account as a security precaution."`
  - 原因：AWS 检测到异常活动，临时锁定账号
  - 解决：联系 AWS 支持解封，或等待自动解锁（通常 24-48 小时）
- `504 Gateway Timeout`: 代理超时或网络问题

**为什么需要这一步**:
- Token 刷新只验证 OIDC 认证是否有效
- 使用量查询只验证会计系统是否可访问
- `ListAvailableModels` 验证 token 是否有**实际的 AI 服务访问权限**，并能从 AWS 获取实时模型数据
- 这是用户明确要求的验证标准："必须向上游大模型发一句话，并得到正常的回复"

## 5. 平台特有注意事项

- AWS OIDC 和 Q API 都位于 `us-east-1` 区域，但 Q API 有 EU 备用节点
- 必须使用 `impersonate="chrome131"` 或类似的 Chrome 指纹，否则 AWS 会拒绝请求
- `User-Agent` 和 `x-amz-user-agent` 必须包含特定格式（参考上面示例），AWS 会校验
- `accessToken` 通常以 `aoaAAAAAGn...` 开头（Base64URL 编码的 JWT）
- `refreshToken` 通常以 `aorAAAAAGpm...` 开头
- `clientSecret` 是 RSA 私钥，解密后可获得 AWS 凭证
- 每个账号的额度上限和订阅计划独立管理
- 额度重置时间通常是 UTC 00:00，按月度或季度周期
