# Git 追踪 9Router 数据变更

## 为什么用 Git

9Router 的核心数据存储在 `/root/src/9router-data/db/data.sqlite`（`providerConnections` 表）和 `/root/src/9router-data/db.json`（备份）。每次导入账号、更新 token、修改连接状态都直接修改这些文件。Git 提供：

- **每次变更可追溯**：谁（commit message）、何时、改了什么
- **安全网**：导入出错可 `git checkout` 回退
- **diff 确认**：`git diff` 验证只改动了预期条目，未破坏已有数据

## 初始化（一次性）

```bash
cd /root/src/9router-data

# 创建 .gitignore（见下方模板）
cat > .gitignore << 'EOF'
# SQLite WAL/SHM (transient, auto-generated)
*.sqlite-wal
*.sqlite-shm

# Stale/legacy DB files
db.json.db
9router.db
db.sqlite

# Backup files
db.json.backup*
db.json.bak*

# Large static files
request-details.json
usage.json

# Runtime artifacts
logs/
runtime/
mitm/
mcp/
update/
__pycache__/
*.log
log.txt
EOF

# 初始化仓库
git init
git config user.name "Hermes Agent"
git config user.email "khchen1985@gmail.com"

# 初始提交（导入前的基线快照）
git add -A
git commit -m "Initial commit: 9Router data baseline (pre-import)"
```

## 标准变更工作流

每次修改 9Router 数据（导入、更新 token、状态变更）后：

```bash
cd /root/src/9router-data

# 1. 检查变更范围
git diff --stat

# 2. 查看具体改动（db.json 可读）
git diff db.json | head -80

# 3. 如果 diff 正确（只新增/修改了预期条目，未删除/破坏已有数据）
git add -A
git commit -m "import: add <email> (ChatGPT Codex)"

# 4. 如果有意外变更（如多余删除、格式破坏）
git restore <file>   # 回退该文件
```

## commit message 规范

```
<action>: <description>

<action>: import | update | remove | config | fix
<description>: 变更的账号/配置项
```

示例：
- `import: add stephaniejenkins@qhvip.cc (ChatGPT Codex)`
- `update: refresh tokens for 3 Codex accounts`
- `remove: delete expired kiro account georgehall@qhvip.cc`
- `config: change proxy pool to iproyal-us-residential`

## 典型变更类型

| 操作 | 影响文件 | commit 类型 |
|------|----------|-------------|
| 导入新账号 | `db/data.sqlite` + `db.json` | `import` |
| 更新 token | `db/data.sqlite` + `db.json` | `update` |
| 删除账号 | `db/data.sqlite` + `db.json` | `remove` |
| 状态变更 | `db/data.sqlite` + `db.json` | `update` |
| 配置文件 | `9router/` 目录下文件 | `config` |

## SQLite WAL 模式陷阱

9Router SQLite 使用 WAL（Write-Ahead Logging）模式。INSERT/UPDATE 后的数据先写入 `data.sqlite-wal`，主 `data.sqlite` 文件在 checkpoint 前不会变化。

**现象**：`git diff --stat` 只显示 `db.json` 变更，`data.sqlite` 显示 `Bin 437252096 -> 437252096`（hash 不变）。

**这是正常的**——数据已在 SQLite 中（可通过 SQL 查询确认），只是尚未 checkpoint。db.json 是此时唯一人类可读的 diff 来源。

**验证数据已写入**：
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/src/9router-data/db/data.sqlite')
cur = conn.execute(\"SELECT email FROM providerConnections WHERE email = '<target>'\")
print('Found:', cur.fetchone())
conn.close()
"
```

## 回退操作

```bash
# 回退最近一次 commit（保留文件改动）
git reset --soft HEAD~1

# 回退文件到上次 commit 状态
git checkout -- <file>

# 查看历史
git log --oneline --stat
```
