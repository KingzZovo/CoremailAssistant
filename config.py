"""Global configuration, paths, and default settings for CoremailAssistant."""

import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent

# 数据与运行时目录
DATA_DIR = BASE_DIR / "data"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
LOGS_DIR = BASE_DIR / "logs"

# 数据库与模型存储路径
DATABASE_PATH = str(DATA_DIR / "assistant.db")
ML_MODELS_PATH = str(DATA_DIR / "ml_models.pkl")

# 确保运行时目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# 默认系统配置项
DEFAULT_SETTINGS = {
    # Coremail IMAP 接收服务
    "imap_host": "mail.example.com",
    "imap_port": "993",
    "imap_ssl": "1",

    # Coremail SMTP 发送服务
    "smtp_host": "mail.example.com",
    "smtp_port": "465",
    "smtp_ssl": "1",

    # 邮箱身份凭证
    "email_account": "",
    "email_password": "",
    "sender_display_name": "",

    # 自动化与后台轮询
    "poll_interval": "60",               # 秒
    "auto_mark_read": "1",              # 1: 自动标记为已读, 0: 保持未读
    "max_fetch_count": "20",            # 单次拉取最大未读数

    # 过滤与智能化模式
    # 模式可选: 'rules_and_ml'(本地规则+机器学习), 'ml_first'(机器学习优先), 'ollama_hybrid'(本地+Ollama混合)
    "filter_mode": "rules_and_ml",

    # 本地大模型 (Ollama) 配置
    "ollama_enabled": "0",              # 1: 启用, 0: 仅使用本地 ML
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "qwen2.5:3b",
    "ollama_timeout": "30",
}
