# any-auto-register 数据库结构

## accounts 表

存储所有平台账号基本信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 自增主键 |
| platform | VARCHAR | 平台标识（如 'kiro', 'chatgpt'） |
| email | VARCHAR | 登录邮箱 |
| password | VARCHAR | 登录密码 |
| user_id | VARCHAR | 平台用户 ID（可选） |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

## account_credentials 表

存储账号的敏感凭证（Token、OAuth 密钥等）。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 自增主键 |
| account_id | INTEGER | 关联 accounts.id |
| scope | VARCHAR | 凭证作用域（platform / email 等） |
| provider_name | VARCHAR | 平台名称 |
| credential_type | VARCHAR | 凭证类型（token / refresh_token / client_id 等） |
| key | VARCHAR | 凭证键名（如 'accessToken', 'refreshToken'） |
| value | VARCHAR | 凭证值（加密或明文） |
| is_primary | BOOLEAN | 是否为主凭证 |
| source | VARCHAR | 数据来源（accounts.extra 等） |
| metadata_json | VARCHAR | 附加元数据（JSON） |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### Kiro 凭证键名映射

| credential_type | key | 说明 |
|----------------|-----|------|
| token | accessToken / access_token | OAuth Access Token（以 `aoaAAAAAGn...` 开头） |
| token | refreshToken | OAuth Refresh Token（以 `aorAAAAAGpm...` 开头） |
| token | clientId | OAuth 客户端 ID（如 `ntutKACwXU-rf5ihAJatNHVzLWVhc3QtMQ`） |
| token | clientSecret | OAuth 客户端密钥（JWT 格式，以 `eyJraW...` 开头） |
| token | legacy_token | 旧版 Token（兼容用） |

## proxies 表

存储静态代理池。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 自增主键 |
| url | VARCHAR | 代理 URL（含认证） |
| region | VARCHAR | 地区标识 |
| success_count | INTEGER | 成功次数 |
| fail_count | INTEGER | 失败次数 |
| is_active | BOOLEAN | 是否启用 |
| last_checked | DATETIME | 最后检测时间 |

## provider_settings 表

存储动态服务提供者配置（邮箱、验证码、代理等）。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 自增主键 |
| provider_type | VARCHAR | 类型（mailbox / captcha / sms / proxy） |
| provider_key | VARCHAR | 标识（如 'yescaptcha_api'） |
| display_name | VARCHAR | 显示名 |
| auth_mode | VARCHAR | 认证模式 |
| enabled | BOOLEAN | 是否启用 |
| is_default | BOOLEAN | 是否为默认 |
| config_json | VARCHAR | 配置（JSON） |
| auth_json | VARCHAR | 认证信息（JSON） |
| metadata_json | VARCHAR | 元数据（JSON） |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

## 常用查询

### 查询所有 Kiro 账号及其凭证

```sql
SELECT 
    a.id,
    a.email,
    a.password,
    ac.key AS cred_key,
    ac.value AS cred_value
FROM accounts a
LEFT JOIN account_credentials ac 
    ON a.id = ac.account_id 
    AND ac.provider_name = 'kiro'
WHERE a.platform = 'kiro'
ORDER BY a.id;
```

### 查询有完整凭证的账号（可验证）

```sql
SELECT DISTINCT a.id, a.email
FROM accounts a
JOIN account_credentials ac ON a.id = ac.account_id
WHERE a.platform = 'kiro'
  AND ac.provider_name = 'kiro'
  AND ac.key IN ('refreshToken', 'clientId', 'clientSecret')
GROUP BY a.id
HAVING COUNT(DISTINCT ac.key) = 3;
```

### 更新代理配置

```sql
UPDATE proxies 
SET 
    url = 'http://user:pass@host:port',
    region = 'iproyal-us',
    is_active = 1,
    last_checked = CURRENT_TIMESTAMP
WHERE id = 1;
```
