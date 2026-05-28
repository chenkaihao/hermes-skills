# 任务强制取消与队列清理（2026-05-26）

## 问题

通过 any-auto-register Web UI 取消任务后，任务卡在 `cancel_requested` 状态，任务运行器不处理取消请求，导致：
- 该任务一直占用队列位置
- 后续新任务排队在 `pending` 状态，永远无法开始
- 服务重启后 `pending` 任务会被标记为 `interrupted`

## 根因

取消 API 只是设置了 `cancel_requested` 状态标志，但任务在阻塞操作中（如等待 SMS 验证码、浏览器交互）时，运行器无法及时检查取消标志，导致卡住。

## 数据库表结构

tasks 表使用 `id` 字段（非 `task_id`）作为主键：

```
sqlite> PRAGMA table_info(tasks);
0|id|VARCHAR|1|null|1
1|type|VARCHAR|1|null|0
2|platform|VARCHAR|1|null|0
3|status|VARCHAR|1|null|0
...
```

## 强制取消步骤

### 1. 查询所有非终态任务

```python
import sqlite3
conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
rows = conn.execute(
    "SELECT id, status FROM tasks WHERE status NOT IN ('failed', 'succeeded', 'interrupted')"
).fetchall()
for r in rows:
    print(r)
conn.close()
```

### 2. 强制标记卡住的任务为 failed

```python
conn = sqlite3.connect('/root/src/any-auto-register/account_manager.db')
conn.execute(
    "UPDATE tasks SET status = 'failed', error = 'Force cancelled by admin - stuck in cancel_requested' WHERE id = ?",
    ('task_1779801446568_00f7c2',)
)
conn.commit()
conn.close()
```

### 3. 重启服务（清空内存中的任务队列 + 加载代码修复）

```bash
systemctl restart any-auto-register
```

**警告**：重启会中断所有 `pending` 任务（标记为 `interrupted`）。确认只有一个待清理的卡住任务再重启。

## 检查方法

```bash
# 通过 API 查看最新任务
curl -s http://localhost:8000/api/tasks | python3 -c "
import json, sys
for t in json.load(sys.stdin)['items'][:5]:
    status = t['status']
    error = (t.get('error') or '-')[:60]
    print(f\"{t['id'][-18:]} | {status:20s} | {t['progress']:5s} | {error}\")
"
```

## 注意事项

1. **数据库直接修改后，服务不会自动感知**——必须重启
2. **重启会中断 pending 任务**——确认没有其他正常的等待中的任务
3. **代码修改后也要重启**——Python 模块在首次 import 时加载，代码 patch 不重启不生效
4. **日志查询**：`journalctl -u any-auto-register --no-pager --since "HH:MM"` 比 API logs 端点更可靠（API 端点可能返回 SPA HTML）
