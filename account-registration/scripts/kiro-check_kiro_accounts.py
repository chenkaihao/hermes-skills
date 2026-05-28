#!/usr/bin/env python3
"""
Kiro 账号可用性检测脚本（使用代理）
三步验证法：Token刷新 → 额度查询 → 真实对话测试 (generateAssistantResponse)

🔥 2026-05-26 更新：加入 generateAssistantResponse 真实对话测试。
仅凭 ListAvailableModels / getUsageLimits 都是假阳性——必须发送真实消息并验证回复。
"""
