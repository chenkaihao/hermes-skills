# Cloudflare 封锁问题

## 现象

服务器直连 ChatGPT API 时，大量请求返回：
```
HTTP 403: {"detail":"Unusual activity has been detected from your device. Try again later. (UUID)"}
```

## 触发条件

- 短时间内大量请求
- 数据中心 IP 被标记
- 缺少完整浏览器指纹

## 缓解措施

### 1. 使用 curl_cffi + 浏览器指纹

```python
from curl_cffi import requests as cffi_requests

session = cffi_requests.Session(impersonate="chrome120", proxy=None)
```

推荐指纹版本：
- `chrome120`（当前使用）
- `chrome110`（备选）

### 2. 增加等待时间

```python
import time
time.sleep(120)  # 等待2分钟后重试
```

封锁通常在 5-10 分钟内缓解。

### 3. 限制请求频率

- 每个账号间隔 1-2 秒
- 避免短时间内集中验证

### 4. 优先使用 9Router

9Router 已处理代理和请求分发，账号只需保证 token 有效。

## 验证策略

由于验证结果波动，建议：
1. 等待 2 分钟后进行最终验证
2. 每个账号验证 2 次，取一致结果
3. 标记为"疑似无效"的账号可次日再验证

## 消息发送的特殊困难

`POST /backend-api/conversation` 在服务器环境下持续失败：
- `422 Invalid conversation body`：请求格式可能已变更或需要额外的 Cookie
- `403 Unusual activity`：Cloudflare 封锁

**结论**：消息发送测试暂缓，通过 9Router 实际使用验证。
