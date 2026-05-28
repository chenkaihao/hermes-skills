# 美国住宅/宽带代理服务商

## 当前使用的代理：IPRoyal

**状态**: ✅ 已充值并配置（2026-05-15，Hillside AT&T 会话）

**配置**:
```
http://4GJSsuSsb3vci2UA:4D9N9XyBb0weKTy8_country-us_city-hillside_session-9ZySUn49_lifetime-30m@geo.iproyal.com:12321
```

**属性**:
- 类型: 住宅代理（Residential Proxy）
- 地区: 美国 Hillside, Illinois（AT&T 家庭宽带 AS7018）
- 出口 IP: 99.103.40.6
- 协议: HTTP/HTTPS
- 认证: 用户名 + 密码（密码含路由参数）
- 端口: 12321

**路由参数**:
| 后缀 | 作用 |
|------|------|
| `_country-us` | 强制美国出口 — **必加**，不加可能路由到沙特/阿尔及利亚 |
| `_city-hillside` | 指定 Hillside, IL 城市 |
| `_session-9ZySUn49` | 固定会话 ID（30分钟内不换 IP） |
| `_lifetime-30m` | 会话有效期 30 分钟 |

**已配置位置** (全部 7 处，详见 `references/proxy-config-verification.md`):
1. 9Router: `db.json` proxyPools + `.env` (×2)
2. any-auto-register: SQLite `proxies` 表 (id=3)
3. kiro-account-validation skill: `scripts/check_kiro_accounts.py` PROXY_CONFIG
4. 批量注册脚本: `auto_register_batch.py` PROXY_URL
5. 传统检测脚本: `/root/kiro_account_check.py`

## 其他可选代理服务商

### Webshare.io
- **特点**: 80M+ 住宅 IP，永久免费套餐（10 个代理）
- **价格**: 住宅代理 $3.50/月起，静态住宅 $6/月起
- **覆盖**: 195 个国家，660 万+ 美国 IP
- **优势**: 最低成本入门，永久免费计划

### Oxylabs
- **特点**: 企业级代理，ISO/IEC 27001:2022 认证
- **价格**: 住宅代理 $6/GB，ISP 代理 $16/月起
- **覆盖**: 195+ 国家
- **优势**: 大规模爬取，免费试用，高稳定性

### Rayobyte
- **特点**: 美国本土代理网络，40M+ 住宅 IP
- **价格**: 住宅代理、轮换 ISP、静态 ISP 多种选择
- **优势**:  Largest US-based 代理网络

### Smartproxy / Decodo
- **特点**: 性价比高，Proxyway 排名第一
- **价格**: 住宅代理约 $4-5/GB
- **覆盖**: 195 国家

## 代理在 any-auto-register 中的使用

### 静态代理池

存储在 `proxies` 表，手动管理:
```sql
SELECT id, url, region, success_count, fail_count, is_active 
FROM proxies 
WHERE is_active = 1;
```

### 动态代理 Provider

通过 `provider_settings` 表配置第三方 API:
- `api_extract`: 从 API 实时获取代理 IP
- `rotating_gateway`: 通过网关自动轮换

**配置示例** (`provider_settings.config_json`):
```json
{
  "proxy_api_url": "https://api.proxyprovider.com/v1/proxy",
  "proxy_protocol": "http",
  "proxy_username": "user",
  "proxy_password": "pass"
}
```

**注意**: any-auto-register 的 Turnstile 验证码浏览器支持代理配置（`--proxy-support`），通过 `proxies.txt` 文件读取。

## 代理在 9Router 中的使用

9Router 本身是 AI 编程工具聚合器，不直接管理代理池。代理通过以下方式影响:

1. **外网 API 请求**: 9Router 配置了代理后，其出站请求（如调用 OpenAI、Claude API）会通过代理
2. **Web 控制台访问**: Nginx 反向代理通过代理访问上游 API
3. **环境变量**: `http_proxy`, `https_proxy`, `all_proxy` 控制进程级代理

## 代理选择建议

| 场景 | 推荐服务商 | 理由 |
|------|-----------|------|
| 账号注册（低频率） | IPRoyal, Webshare | 成本低，住宅 IP 质量好 |
| 大规模爬取 | Oxylabs, Bright Data | 企业级稳定性 |
| 低成本测试 | Webshare 免费套餐 | 零成本验证 |
| 轮换需求 | Smartproxy/Decodo | 自动轮换 IP |

## 代理验证脚本

使用 Kiro 账号检测脚本验证代理连通性:

```bash
# 不传代理 → 直接连接
python scripts/check_kiro_accounts.py

# 指定代理 → 走代理
PROXY="http://user:pass@geo.iproyal.com:12321" python scripts/check_kiro_accounts.py
```

脚本会尝试美国 `oidc.us-east-1.amazonaws.com` 和欧洲 `q.eu-central-1.amazonaws.com` 两个端点。
