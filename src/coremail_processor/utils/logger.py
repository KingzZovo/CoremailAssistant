"""Logger utility module using Loguru."""

import sys
from pathlib import Path
from loguru import logger


def setup_logger(log_dir: str = "./logs", level: str = "INFO", rotation: str = "10 MB", retention: str = "14 days"):
    """配置控制台与文件日志输出，确保在 Windows 终端下 UTF-8 编码不乱码"""
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)

    # 移除默认 handler
    logger.remove()

    # 控制台彩色输出 (Windows 兼容)
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # 文件日志输出
    log_file = path / "coremail_processor_{time:YYYY-MM-DD}.log"
    logger.add(
        str(log_file),
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
    )

    return logger
