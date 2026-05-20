# Provider Instructions — 如何向我方导入账号

## 一、准备工作

### Windows 用户
1. 下载 Python: https://www.python.org/downloads/ （选 3.8+，安装时勾选 "Add Python to PATH"）
2. 打开命令提示符 (Win+R → 输入 `cmd`)
3. 验证: `python --version`

### Mac 用户
```bash
python3 --version  # 已内置
```

### 下载脚本
```
https://tokenfree.cc/report/import_accounts.py
```
另存为任意目录即可。

## 二、准备账号数据

### 方式 1：如果你有 9Router 导出的 JSON（推荐）

直接使用 9Router 导出的文件，无需任何修改：
```bash
python import_accounts.py --input 你的9router导出.json --push
```

### 方式 2：手动整理 JSON

创建 `accounts.json`:
```json
{
  "codex": [
    {
      "email": "account1@example.com",
      "refreshToken": "rt_xxx...xxx",
      "accessToken": "eyJ...",
      "expiresAt": "2026-06-15T00:00:00Z",
      "name": "Account 1"
    }
  ]
}
```

### 方式 3：Excel 转 CSV

1. Excel 中设置表头: `email,refreshToken,accessToken,platform,expiresAt`
2. 另存为 CSV (UTF-8)
3. 运行: `python import_accounts.py --input accounts.csv --push`

## 三、运行

```bash
# 1. 先预览（安全，不导入）
python import_accounts.py --input accounts.json --dry-run

# 2. 确认无误后推送
python import_accounts.py --input accounts.json --push
```

## 四、常见问题

| 问题 | 解决 |
|------|------|
| "python 不是内部命令" | 重新安装 Python 并勾选 Add to PATH |
| "文件不存在" | 确认文件路径，Windows 用 `accounts.json` 而非 `C:\Users\...` |
| "无法识别格式" | 联系我方，提供你的数据样例 |
| "Token 格式异常" | 检查 token 是否完整（未截断） |
| "网络错误" | 检查是否能访问 https://tokenfree.cc |
