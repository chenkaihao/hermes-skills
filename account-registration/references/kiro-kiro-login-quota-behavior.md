# Kiro 登录与额度行为分析

**测试时间**: 2026-05-12  
**测试目标**: 验证 50 额度账号通过登录是否能获得 500 freeTrial

---

## 关键发现

### freeTrial 状态由 AWS 服务器端控制

| 账号类型 | baseLimit | freeTrial | totalLimit | freeTrialStatus |
|----------|-----------|-----------|------------|-----------------|
| 高额度账号 (6个) | 50 | 500 | 550 | `ACTIVE` |
| 低额度账号 (7个) | 50 | 0 | 50 | `None` |

**freeTrialInfo 原始响应对比**:

```json
// 有 freeTrial 的账号
{
  "freeTrialInfo": {
    "freeTrialStatus": "ACTIVE",
    "usageLimit": 500,
    "currentUsage": 0,
    "freeTrialExpiry": 1779905173.686
  }
}

// 只有 50 额度的账号
{
  "freeTrialInfo": null
}
```

**结论**: freeTrial 的有无是 **AWS 账号属性**，无法通过代码、登录或 token 操作改变。

---

## 登录方法测试结果

### 方法 1: Token 刷新（`refresh_kiro_token` + `fetch_kiro_status_with_token`）

**状态**: ✅ 成功  
**结果**: accessToken 刷新成功，额度查询正常，但 **freeTrial 状态不变**  
**适用场景**: 验证 token 有效性、查询当前额度  
**局限性**: 无法激活新账号或改变账号属性

### 方法 2: 协议登录（`KiroRegister.login_for_tokens`）

**状态**: ❌ 失败  
**失败原因**: AWS signin 流程要求 **OTP 验证码**  
**流程**: email → password → OTP → tokens  
**错误点**: 密码提交成功 (200) → 跳转到 `get-email-otp-login-credential` 步骤 → 无 OTP callback → 失败

**日志示例**:
```
login 4: 提交密码...
  POST https://us-east-1.signin.aws/.../get-password
  Status: 200
  → sid=get-email-otp-login-credential
⚠️ AWS 要求 OTP 验证: get-email-otp-login-credential
❌ 未提供 otp_callback, 无法处理 OTP
```

### 方法 3: 浏览器自动化登录（`KiroBrowserLogin`）

**状态**: ❌ 失败  
**失败原因**: 同样需要 OTP，且浏览器无法自动获取验证码  
**流程**: 填写邮箱 → 填写密码 → 检测 OTP 输入框 → 等待 OTP callback → 提交  
**卡点**: `wait_otp` 状态持续等待，超时 120 秒

**日志示例**:
```
[login] url=... state=wait_password
已填写邮箱: calebzhang88@qhvip.cc
[login] url=... state=wait_password  ← 循环，密码框未出现或提交后跳OTP
```

---

## OTP 自动化障碍

### any-auto-register 的 OTP 获取机制

1. **Laoudo 邮箱**: `wait_for_otp()` 轮询 `laoudo.com` API 获取验证码
2. **CFWorker 邮箱**: 通过 `provider_resources` 中的 mailbox 配置自动获取
3. **手动输入**: 控制台交互式输入

### 测试账号的邮箱域名

| 域名 | 数量 | OTP 自动化支持 |
|------|------|----------------|
| qhvip.cc | 18 | ❌ 无配置 |
| hq.accesswiki.net | 1 | ❌ 无配置 |
| tr.26ai.org | 1 | ❌ 无配置 |
| qq.com | 1 | ❌ 无配置 |

**所有测试账号均不支持自动 OTP 获取**。

---

## 账号差异分析

### 数据对比（2026-05-12 实时检测）

| 维度 | 高额度账号 (ID 7,9-12,15) | 低额度账号 (ID 22-28) |
|------|--------------------------|----------------------|
| **注册时间** | 2026-04-27 ~ 2026-05-06 | 2026-05-08 |
| **邮箱域名** | qhvip.cc, tr.26ai.org | qhvip.cc, hq.accesswiki.net |
| **baseLimit** | 50 | 50 |
| **freeTrial** | 500 | 0 |
| **totalLimit** | 550 | 50 |
| **凭证完整度** | refreshToken + clientId/Secret | refreshToken + clientId/Secret |
| **freeTrialStatus** | `ACTIVE` | `None` |

**观察**: 高额度账号注册时间更早（4月27日~5月6日），低额度账号集中在5月8日注册。

**假设**:
- AWS 可能对新注册账号调整了 freeTrial 政策
- 5月8日后注册的账号不再自动获得 500 freeTrial
- 账号属性（邮箱域名、IP 段）可能影响 freeTrial 授予

---

## 诊断脚本

```python
# diagnose_kiro_quota.py - 诊断账号额度差异
import sys
sys.path.insert(0, '/root/src/any-auto-register')

from platforms.kiro.usage import _fetch_usage
from platforms.kiro.switch import refresh_kiro_token
import sqlite3

def diagnose_account(acc_id: int):
    db_path = '/root/src/any-auto-register/account_manager.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT a.email, ac.key, ac.value
        FROM accounts a
        LEFT JOIN account_credentials ac ON a.id = ac.account_id
        WHERE a.id = ? AND ac.key IN ('refreshToken', 'clientId', 'clientSecret')
    """, (acc_id,))
    
    creds = {}
    for row in cursor.fetchall():
        creds[row[1]] = row[2]
    conn.close()
    
    # 刷新 token
    ok, token = refresh_kiro_token(creds.get('refreshToken'), creds.get('clientId'), creds.get('clientSecret'))
    if not ok:
        print(f"❌ Token 刷新失败: {token.get('error')}")
        return
    
    # 查询原始数据
    raw = _fetch_usage(token['accessToken'])
    if raw is None:
        print("❌ API 请求失败")
        return
    
    # 分析 freeTrial
    breakdown = raw.get('usageBreakdownList', [])
    credit_item = next((x for x in breakdown if x.get('resourceType') == 'CREDIT'), None)
    
    if credit_item:
        ft = credit_item.get('freeTrialInfo')
        print(f"freeTrialInfo: {ft}")
        print(f"base: {credit_item.get('usageLimitWithPrecision')} / {credit_item.get('currentUsageWithPrecision')}")
    else:
        print("❌ 未找到 CREDIT 条目")

# 使用
diagnose_account(22)  # 低额度账号
diagnose_account(7)   # 高额度账号
```

---

## 建议

### 对于只有 50 额度的账号

1. **手动激活尝试**: 在 Kiro Web 门户 (`app.kiro.dev`) 手动登录，看是否触发 freeTrial 激活
2. **等待观察**: 部分账号可能在注册后 24-48 小时自动获得 freeTrial
3. **联系 AWS 支持**: 如果是政策限制，官方渠道确认

### 对于自动化场景

- **优先使用已有 freeTrial 的账号** (ID 7, 9, 10, 11, 12, 15)
- 定期（每周）重新检测所有账号的 freeTrial 状态变化
- 将 freeTrialStatus 纳入账号健康度评估

---

## 参考代码位置

| 函数/类 | 文件 | 行号 |
|---------|------|------|
| `KiroRegister.login_for_tokens` | `platforms/kiro/core.py` | 1555 |
| `KiroBrowserLogin.run` | `platforms/kiro/browser_register.py` | 1733 |
| `refresh_kiro_token` | `platforms/kiro/switch.py` | 80 |
| `_fetch_usage` | `platforms/kiro/usage.py` | 16 |
| `_parse_usage` | `platforms/kiro/usage.py` | 37 |
| `wait_for_otp` | `platforms/kiro/core.py` | 1845 |
