"""Configuration manager and schemas."""

import os
from pathlib import Path
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field
import yaml
from dotenv import load_dotenv

# 加载 .env 环境变量
load_dotenv()


class MailServerConfig(BaseModel):
    imap_host: str = Field(default_factory=lambda: os.getenv("COREMAIL_SERVER", "mail.example.com"))
    imap_port: int = Field(default_factory=lambda: int(os.getenv("COREMAIL_IMAP_PORT", 993)))
    use_ssl: bool = True
    smtp_host: Optional[str] = Field(default_factory=lambda: os.getenv("COREMAIL_SMTP_SERVER"))
    smtp_port: int = Field(default_factory=lambda: int(os.getenv("COREMAIL_SMTP_PORT", 465)))
    smtp_use_ssl: bool = True
    username: str = Field(default_factory=lambda: os.getenv("COREMAIL_USERNAME", ""))
    password: str = Field(default_factory=lambda: os.getenv("COREMAIL_PASSWORD", ""))
    folder: str = "INBOX"


class SchedulerConfig(BaseModel):
    poll_interval: int = Field(default_factory=lambda: int(os.getenv("COREMAIL_POLL_INTERVAL", 60)))
    batch_size: int = 20
    mark_as_read: bool = True
    move_to_folder: Optional[str] = None


class StorageConfig(BaseModel):
    attachment_dir: str = "./attachments"
    output_dir: str = "./output"
    log_dir: str = "./logs"


class LoggingConfig(BaseModel):
    level: str = Field(default_factory=lambda: os.getenv("COREMAIL_LOG_LEVEL", "INFO"))
    rotation: str = "10 MB"
    retention: str = "14 days"


class AppConfig(BaseModel):
    mail_server: MailServerConfig = Field(default_factory=MailServerConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    rules_file: str = "./config/rules.yaml"


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """从 yaml 文件加载配置，若文件不存在则尝试读取 example 配置或环境变量"""
    paths_to_try = [
        config_path,
        "config/config.yaml",
        "config/config.example.yaml",
    ]

    for p in paths_to_try:
        if p and Path(p).exists():
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return AppConfig(**data)

    return AppConfig()
