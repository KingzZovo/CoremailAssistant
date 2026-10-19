"""Global configuration constants, directory paths, and default settings for CoremailAssistant."""

import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent

# 数据与运行时目录
DATA_DIR = BASE_DIR / "data"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
LOGS_DIR = BASE_DIR / "logs"

# 数据库与本地机器学习模型存储路径
DATABASE_PATH = str(DATA_DIR / "assistant.db")
ML_MODELS_PATH = str(DATA_DIR / "ml_models.pkl")

# 自动创建必要目录
DATA_DIR.mkdir(parents=True, exist_ok=True)
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# 默认系统配置项字典（用于数据库首次初始化或配置回退）
DEFAULT_SETTINGS = {
    # 论客邮箱 (Coremail) 协议与统一服务器配置 (适配论客客户端专用协议与单地址模式)
    "protocol_mode": "coremail",         # 'coremail': 专用单地址协议 (同论客客户端), 'imap_smtp': 标准手动端口
    "coremail_server": "",               # Coremail 统一服务器地址 (IP或域名)
    "http_base_url": "",                 # Coremail WebAPI 探测或指定的根 URL (如 http://10.x.x.x:8080)

    # 论客邮箱 (Coremail) IMAP 收信服务
    "imap_host": "mail.example.com",
    "imap_port": "993",
    "imap_ssl": "1",                     # 1: 启用 SSL, 0: 普通

    # 论客邮箱 (Coremail) SMTP 发信服务
    "smtp_host": "mail.example.com",
    "smtp_port": "465",
    "smtp_ssl": "1",                     # 1: 启用 SSL, 0: 普通

    # 账号凭据
    "email_account": "",
    "email_password": "",
    "sender_display_name": "",

    # 自动化与后台轮询
    "poll_interval": "60",               # 后台自动收信轮询间隔 (秒)
    "auto_mark_read": "0",              # 1: 流转后自动标记已读, 0: 保持原状态
    "max_fetch_count": "30",            # 单次拉取最大历史未读数

    # 过滤与智能化筛选模式
    # 可选值:
    #   'rules_and_ml': 优先规则匹配，未命中则调用本地机器学习
    #   'ml_only': 仅使用本地全文机器学习
    #   'rules_only': 仅使用规则匹配
    #   'ollama_hybrid': 本地初筛命中后调用 Ollama 大模型深度润色
    "filter_mode": "rules_and_ml",

    # 本地大模型 (Ollama) 配置
    "ollama_enabled": "0",              # 1: 启用, 0: 禁用
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "qwen2.5:3b",
    "ollama_timeout": "30",

    # 默认发信抄送习惯
    "default_include_sender_in_cc": "1", # 1: 默认抄送原发件人, 0: 不抄送
}
