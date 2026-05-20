# 账号导入 JSON Schema

## 请求格式

```json
{
  "kiro": [
    {
      "email": "user@example.com",
      "name": "Account 1",
      "refreshToken": "rt.1.AAA...",
      "accessToken": "eyJhbG...",
      "expiresAt": "2026-06-15T00:00:00Z",
      "clientId": "xxx",
      "clientSecret": "xxx"
    }
  ],
  "codex": [
    {
      "email": "user@example.com",
      "name": "Account 2",
      "refreshToken": "rt_xxx...xxx",
      "accessToken": "eyJhbG...",
      "expiresAt": "2026-06-15T00:00:00Z"
    }
  ],
  "chatgpt": [...],
  "claude": [...]
}
```

## 响应格式

```json
{
  "success": true,
  "stats": {
    "kiro": {"new": 3, "updated": 1},
    "codex": {"new": 5, "updated": 2}
  },
  "total": 11,
  "phase": "validating"
}
```

## 字段说明

| 字段 | 必填 | 格式 | 说明 |
|------|:---:|------|------|
| email | ✅ | `user@domain` | 唯一标识，同一邮箱视为同一账号 |
| name | ❌ | string | 账号名称，默认取邮箱前缀 |
| refreshToken | ✅⍟ | string | 用于刷新 accessToken（OAuth） |
| accessToken | ✅⍟ | string | 当前有效 token |
| expiresAt | ❌ | ISO 8601 | token 过期时间 |
| clientId | kiro | string | Kiro AWS Builder ID |
| clientSecret | kiro | string | Kiro AWS Builder ID 密钥 |

> ⍟ refreshToken 和 accessToken 至少提供一个
