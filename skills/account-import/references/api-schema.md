# Import API Schema

## Request

```
POST https://tokenfree.cc/import/api/upload
Content-Type: application/json
```

### Body

```json
{
  "kiro": [
    {
      "email": "user@example.com",
      "name": "Account Name",
      "refreshToken": "rt.1.AAA...",
      "accessToken": "eyJ...",
      "expiresAt": "2026-06-15T00:00:00Z",
      "clientId": "xxx",
      "clientSecret": "xxx"
    }
  ],
  "codex": [
    {
      "email": "user@example.com",
      "name": "Account Name",
      "refreshToken": "rt_xxx...xxx",
      "accessToken": "eyJ...",
      "expiresAt": "2026-06-15T00:00:00Z"
    }
  ]
}
```

### Fields

| Field | Required | Type | Notes |
|-------|:--------:|------|-------|
| email | ✅ | string | Unique identifier |
| refreshToken | ⍟ | string | At least one of refreshToken or accessToken required |
| accessToken | ⍟ | string | |
| name | ❌ | string | Defaults to email prefix |
| expiresAt | ❌ | ISO 8601 | Token expiry |
| clientId | kiro only | string | AWS Builder ID |
| clientSecret | kiro only | string | AWS Builder ID secret |

## Response

### Success

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

### Error

```json
{
  "error": "Error message"
}
```

## Status Polling

```
GET https://tokenfree.cc/import/api/status
```

### Response

```json
{
  "running": false,
  "phase": "validating",
  "progress": 10,
  "total": 11,
  "valid_count": 9,
  "results": [
    {"name": "Account 1", "email": "...", "valid": true, "detail": "9Router 验证通过 ✓"},
    {"name": "Account 2", "email": "...", "valid": false, "detail": "HTTP 403"}
  ],
  "logs": ["收到 JSON 数据", "导入完成: ...", "验证完成: 9/11 可用"]
}
```
