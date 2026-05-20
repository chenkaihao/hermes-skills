# Hermes Skills

可复用的 Hermes / Claude Code / OpenClaw 技能集合。

## 一键安装

```bash
# 克隆仓库
git clone https://github.com/chenkaihao/hermes-skills.git ~/.hermes/skills-repo

# 安装 account-import 技能
ln -s ~/.hermes/skills-repo/account-import ~/.hermes/skills/automation/account-import
```

## 可用技能

### account-import — 第三方账号导入

将外部提供的账号（JSON/CSV）批量导入 9Router 系统。

- **跨平台**：Windows / macOS / Linux，仅需 Python 3.8+
- **零依赖**：纯标准库，无需 pip install
- **脚本/AI 分离**：确定性操作由脚本完成，AI 仅介入格式理解和异常诊断

```bash
python account-import/scripts/import_accounts.py --input accounts.json --push
```
