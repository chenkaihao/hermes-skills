# 9Router 账号导入 Web 工具

## 概览

基于 Flask 的 Web 工具，提供拖拽上传 JSON 账号文件、自动导入 9Router SQLite、异步验证可用性、实时展示结果的完整流程。

**访问地址**: `https://tokenfree.cc/import/`

## 架构

```
Browser (drag-drop) → Nginx /import/ → Flask :8500 → 9Router SQLite
                                   ↕
                             9Router :9000 (验证)
```

### 组件

| 组件 | 路径 | 说明 |
|------|------|------|
| Flask 后端 | `/root/import-tool/server.py` | 端口 8500，接收上传、导入、异步验证 |
| 前端页面 | `/root/import-tool/templates/index.html` | 拖拽上传、进度轮询、结果表格 |
| 上传暂存 | `/root/import-tool/uploads/` | 上传文件临时存储 |
| systemd | `/etc/systemd/system/import-tool.service` | 自动重启 |
| Nginx | `/etc/nginx/sites-enabled/clawra` → `/import/` | 反向代理 |

## API 端点

### POST /import/api/upload
上传 JSON 文件，触发导入 + 异步验证。立即返回（不等待验证完成）。

**请求**: `multipart/form-data`，字段 `file`（.json）

**响应**:
```json
{
  "success": true,
  "stats": {"kiro": {"new": 3, "updated": 23}, "codex": {"new": 5, "updated": 40}},
  "total": 71,
  "phase": "validating"
}
```

### GET /import/api/status
轮询验证进度。

**响应**:
```json
{
  "running": true,
  "phase": "validating",
  "progress": 15,
  "total": 71,
  "valid_count": 12,
  "results": [
    {"id": "uuid", "provider": "kiro", "name": "Account 1", "email": "...",
     "action": "updated", "valid": true, "detail": "9Router 验证通过 ✓"}
  ],
  "logs": ["[12:30:00] 收到文件...", "[12:30:01] 导入完成..."],
  "stats": {"kiro": {"new": 3, "updated": 23}, ...}
}
```

## 导入逻辑

### 处理流程
1. **解析 JSON** — 读取 `kiro[]` 和 `codex[]` 数组
2. **去重** — 按 `email` 在 `providerConnections` 表中查找已存在连接
3. **构建 data JSON** — 对于 Kiro 账号，构造含 `providerSpecificData`（clientId/clientSecret/authMethod/region）的完整 JSON
4. **写入 SQLite** — `providerConnections` 表，新账号 INSERT，已有账号 UPDATE
5. **重启 9Router** — `systemctl restart 9router`
6. **异步验证** — 逐个通过 `http://localhost:9000/v1/chat/completions` 测试

### Kiro data JSON 结构
```json
{
  "testStatus": "untested",
  "backoffLevel": 0,
  "accessToken": "aoaAAAAA...",
  "refreshToken": "aorAAAAA...",
  "expiresAt": "1970-01-01T00:00:00.000Z",
  "displayName": "",
  "proxyId": "iproyal-us-residential",
  "providerSpecificData": {
    "clientId": "mnGlpAMzP3DYINr7mAKRw3VzLWVhc3QtMQ",
    "clientSecret": "eyJraW...",
    "authMethod": "builder-id",
    "provider": "BuilderId",
    "region": "us-east-1",
    "proxyPoolId": "iproyal-us-residential"
  }
}
```

### Codex data JSON 结构
```json
{
  "testStatus": "untested",
  "backoffLevel": 0,
  "accessToken": "eyJhbG...",
  "refreshToken": "rt_IQChi...",
  "expiresAt": "2026-05-22T06:53:37+00:00",
  "displayName": "",
  "proxyId": "iproyal-us-residential"
}
```

## 验证方法

验证通过 9Router 本地 API 进行（而非直接调上游），这样可以：
- 走 9Router 的 token 自动刷新逻辑
- 走 9Router 的代理池
- 反映实际生产可用性

### Kiro 验证
```python
POST http://localhost:9000/v1/chat/completions
{"model": "kr/claude-haiku-4.5", "messages": [{"role":"user","content":"1+1"}], "max_tokens": 3, "stream": false}
Authorization: Bearer sk-9router
```

### Codex 验证
```python
POST http://localhost:9000/v1/chat/completions
{"model": "cx/gpt-5.5", "messages": [{"role":"user","content":"1+1"}], "max_tokens": 3, "stream": false}
Authorization: Bearer sk-9router
```

## 常见问题

### 验证返回 403
- Kiro: 账号被 AWS 暂停（"temporarily is suspended"），需联系 Kiro 支持解除
- Codex: 账号被封或 token 过期

### Token 刷新失败 401 Bad credentials
Kiro 账号缺少 `clientId`/`clientSecret` 或 refreshToken 已过期。确认导出文件包含这两个字段。

### 验证超时
- 9Router 需要时间重启和加载新连接（约 5-10 秒）
- 某些账号首次请求较慢（token 刷新 + AWS 延迟）
- 验证每个账号约 5-25 秒

## 部署

```bash
# 安装依赖
pip3 install flask

# systemd 服务
cat > /etc/systemd/system/import-tool.service << EOF
[Unit]
Description=9Router Import Tool
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/import-tool
ExecStart=/path/to/python3 /root/import-tool/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now import-tool

# Nginx
location /import/ {
    rewrite ^/import/?(.*)$ /$1 break;
    proxy_pass http://127.0.0.1:8500;
    proxy_set_header Host $host;
    client_max_body_size 50m;
}
```
