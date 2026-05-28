# CF Worker Email Recovery (mail.qhvip.cc)

恢复 `mail.qhvip.cc` DNS 和 CF Worker 自定义域名绑定，使 Kiro 注册的 OTP 验证码自动化流程重新可用。

## 故障症状

| 症状 | 原因 | 诊断命令 |
|------|------|----------|
| `dig mail.qhvip.cc A +short` 无输出 | DNS CNAME 记录丢失 | `dig mail.qhvip.cc A +short` |
| DNS 解析到 CF IP 但 HTTP 522 | Worker 自定义域名绑定丢失 | `curl -s https://mail.qhvip.cc/` 返回 `error code: 522` |
| Worker 返回 "Invalid address credential" | Admin token 过期 | `curl -H "x-admin-auth: kiro2024!@" ...` 返回 401 |

## 恢复步骤

### 1. 确认 Worker 存活

```bash
curl -s https://temp-email.khchen1985.workers.dev/
# 应返回: OK
```

如果 Worker 返回错误或不可达 → 登录 Cloudflare 检查 Worker 状态。

### 2. 恢复 DNS + 自定义域名

**场景 A：DNS 记录丢失（NXDOMAIN）**

Cloudflare 控制台 → `qhvip.cc` → DNS → Add record：
- Type: `CNAME`
- Name: `mail`
- Target: `temp-email.khchen1985.workers.dev`
- Proxy: ✅ 橙色云朵

等待 1-2 分钟后验证：`dig mail.qhvip.cc A +short`（应返回 CF 代理 IP）。

**场景 B：Worker 自定义域名丢失（522）**

⚠️ **关键陷阱**：不能直接添加自定义域名！如果 DNS 中已有手动 CNAME 记录指向 Worker，Cloudflare 会报错：`Hostname 'mail.qhvip.cc' already has externally managed DNS records`。

正确顺序：
1. **先删除** DNS 中的 `mail` CNAME 记录（qhvip.cc → DNS → Records → 删除 mail 条目）
2. **再到 Worker** Triggers → Custom Domains → Add Custom Domain → 输入 `mail.qhvip.cc`
3. Cloudflare 自动创建正确的 DNS 记录

验证：`curl -s https://mail.qhvip.cc/` → 返回 `OK`

### 3. 验证 API

```bash
# Admin token 不变: kiro2024!@
curl -s "https://mail.qhvip.cc/admin/mails?address=roberts@qhvip.cc&limit=5" \
  -H "x-admin-auth: kiro2024!@"
```

### 4. 同步数据库中的 API URL

DNS 恢复后，any-auto-register 数据库中的 API URL 也需要更新——旧记录仍指向 `temp-email.khchen1985.workers.dev`（国内可能被墙）：

```python
import sqlite3, json

db = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
c = db.cursor()

# 更新 provider_settings
c.execute("SELECT id, config_json FROM provider_settings WHERE provider_key='cfworker_admin_api'")
row = c.fetchone()
if row:
    cfg = json.loads(row[1])
    cfg['cfworker_api_url'] = 'https://mail.qhvip.cc'
    c.execute("UPDATE provider_settings SET config_json = ? WHERE id = ?",
              (json.dumps(cfg), row[0]))

# 更新所有 cfworker 资源的 metadata
c.execute("SELECT id, metadata_json FROM provider_resources WHERE provider_name IN ('cfworker', 'cfworker_admin_api')")
for r in c.fetchall():
    meta = json.loads(r[1])
    if meta.get('api_url', '').startswith('https://temp-email.khchen1985.workers.dev'):
        meta['api_url'] = 'https://mail.qhvip.cc'
        c.execute("UPDATE provider_resources SET metadata_json = ? WHERE id = ?",
                  (json.dumps(meta), r[0]))

db.commit(); db.close()
```

## Admin 凭据

| 字段 | 值 | 用途 |
|------|-----|------|
| `x-admin-auth` header | `kiro2024!@` | 所有 Admin API 的认证头 |
| API endpoints | `GET /admin/mails`, `POST /admin/new_address` | 查邮件 / 创建新邮箱 |

Per-address tokens（数据库中各邮箱资源存储的 token）仅在创建邮箱时由 Worker 生成，Admin API 不需要它们。

## 注意

- **workers.dev 域名可能在国内容易被墙**——这就是为什么要用自定义域名 `mail.qhvip.cc`
- 即使 workers.dev 在服务器端 curl 可达（如我们的服务器），用户浏览器打不开不要慌——Cloudflare 控制台的管理功能不受影响
- `provider_settings` 和 `provider_resources` 两个表都需要更新 API URL，漏掉任何一个都会导致部分流程失败
