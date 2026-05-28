# Hermes Skills

可复用 Hermes Agent 技能集合，由 [@chenkaihao](https://github.com/chenkaihao) 维护。

## 一键安装

```bash
git clone https://github.com/chenkaihao/hermes-skills.git ~/.hermes/hermes-skills-repo

# 安装所有技能
for skill in ~/.hermes/hermes-skills-repo/*/; do
  name=$(basename "$skill")
  ln -sf "$skill" ~/.hermes/skills/automation/"$name"
done
```

## 可用技能

### account-import — 第三方账号导入
将外部提供的账号（JSON/CSV）批量导入 9Router 系统。
- **跨平台**：Windows / macOS / Linux，仅需 Python 3.8+
- **零依赖**：纯标准库
```bash
python account-import/scripts/import_accounts.py --input accounts.json --push
```

### account-registration — 自动账号注册
多平台账号批量注册（headed/headless 浏览器模式、邮箱/手机验证、OAuth 流程）。
- 支持平台：ChatGPT、Kiro、Windsurf
- 包含 50+ 平台陷阱文档
- 注册后自动同步到 9Router

### account-health-check — 账号健康检查
验证 9Router 中特定账号是否健康可用。
- 快速检查：OAuth 刷新 + 普通 LLM 调用
- 定向检查：隔离目标账号后做真实 LLM 调用
- 禁止使用 `api.openai.com` 付费端点

### batch-account-registration — 定时批量注册
定时批量自动注册 Kiro + ChatGPT 账号。每 5-10 分钟随机间隔。

## 配置文件

- `hermes-config/SOUL.md` — Hermes Agent 人格定义
- `hermes-config/config.yaml.template` — 配置模板（已脱敏）
- `hermes-config/cron/` — 定时任务定义

## 不应提交到此仓库的内容

- 密钥和 API key（永远不提交）
- 大二进制文件（数据库、日志）
- 缓存文件
