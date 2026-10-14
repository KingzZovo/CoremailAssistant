"""Command line entrypoint for Coremail Auto Processor."""

import argparse
import sys
import time
from typing import Optional
from loguru import logger

from .config import load_config, AppConfig
from .utils.logger import setup_logger
from .client.imap_client import CoremailIMAPClient
from .parser.mail_parser import MailParser
from .rules.rule_engine import RuleEngine
from .actions.base import ActionExecutor


def process_mailbox_once(config: AppConfig, rule_engine: RuleEngine, dry_run: bool = False):
    """执行单次收件箱扫描和规则处理"""
    if not config.mail_server.username or not config.mail_server.password:
        logger.error("未配置邮箱用户名或密码，请检查 config.yaml 或 .env 文件")
        return

    try:
        with CoremailIMAPClient(config.mail_server) as client:
            client.select_folder(config.mail_server.folder)
            uids = client.fetch_unread_uids(limit=config.scheduler.batch_size)

            if not uids:
                logger.info("未发现新的未读邮件")
                return

            action_executor = ActionExecutor(config, client if not dry_run else None)

            for uid in uids:
                try:
                    raw_bytes = client.fetch_email_raw(uid)
                    email = MailParser.parse_bytes(raw_bytes, uid=uid)
                    logger.info(f"正在处理邮件: [{email.subject}] 来自: <{email.sender}> (UID: {uid})")

                    matched_rules = rule_engine.match(email)
                    if not matched_rules:
                        logger.info(f"邮件 [{email.subject}] 无匹配规则")
                        if config.scheduler.mark_as_read and not dry_run:
                            client.mark_as_read(uid)
                        continue

                    for rule in matched_rules:
                        logger.info(f"执行规则: [{rule.name}]")
                        for action in rule.actions:
                            if dry_run:
                                logger.info(f"[DRY-RUN 试运行] 将执行动作: {action.type} -> {action.params}")
                            else:
                                action_executor.execute_action(action, email)

                    # 全局移动文件夹规则
                    if config.scheduler.move_to_folder and not dry_run:
                        client.move_email(uid, config.scheduler.move_to_folder)

                except Exception as e:
                    logger.error(f"处理邮件 UID {uid} 发生异常: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"连接或处理论客邮箱时发生错误: {e}")


def main():
    parser = argparse.ArgumentParser(
        prog="coremail-processor",
        description="Windows 环境下论客邮箱 (Coremail) 邮件自动化处理工具"
    )
    parser.add_argument("-c", "--config", type=str, default=None, help="配置文件路径 (默认查找 config/config.yaml)")
    parser.add_argument("-r", "--rules", type=str, default=None, help="规则文件路径 (默认查找 config/rules.yaml)")
    parser.add_argument("--once", action="store_true", help="仅执行一次检查后退出")
    parser.add_argument("--dry-run", action="store_true", help="试运行模式，只匹配不修改邮件状态和保存文件")
    parser.add_argument("--interval", type=int, default=None, help="覆盖轮询间隔时间 (秒)")

    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)
    setup_logger(
        log_dir=config.storage.log_dir,
        level=config.logging.level,
        rotation=config.logging.rotation,
        retention=config.logging.retention,
    )

    logger.info("=" * 50)
    logger.info("论客邮箱 (Coremail) 邮件自动化处理工具 正在启动")
    logger.info("=" * 50)

    # 加载规则
    rules_path = args.rules or config.rules_file
    rule_engine = RuleEngine(rules_path)

    poll_interval = args.interval or config.scheduler.poll_interval

    if args.once:
        logger.info("当前为单次执行模式 (--once)")
        process_mailbox_once(config, rule_engine, dry_run=args.dry_run)
        logger.info("处理完成，退出程序")
        return

    logger.info(f"启动持续监控守护进程，轮询间隔: {poll_interval} 秒 (按 Ctrl+C 停止)")
    try:
        while True:
            process_mailbox_once(config, rule_engine, dry_run=args.dry_run)
            logger.debug(f"等待 {poll_interval} 秒后进行下一次检查...")
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("收到退出信号，程序正常关闭。")


if __name__ == "__main__":
    main()
