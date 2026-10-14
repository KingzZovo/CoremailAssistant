"""Action handlers for matched email rules."""

from pathlib import Path
from datetime import datetime
import re
from typing import Optional
from loguru import logger
from ..parser.mail_parser import ParsedEmail
from ..rules.rule_engine import RuleAction
from ..client.imap_client import CoremailIMAPClient
from ..config import AppConfig


class ActionExecutor:
    """规则动作执行器"""

    def __init__(self, config: AppConfig, client: Optional[CoremailIMAPClient] = None):
        self.config = config
        self.client = client

    def execute_action(self, action: RuleAction, email: ParsedEmail):
        action_type = action.type.lower()
        params = action.params

        if action_type == "save_attachments":
            self._handle_save_attachments(email, params)
        elif action_type == "mark_read":
            self._handle_mark_read(email)
        elif action_type == "move_folder":
            self._handle_move_folder(email, params)
        elif action_type == "log":
            msg = params.get("message", f"已匹配规则动作: {action_type}")
            logger.info(f"[{email.subject}] {msg}")
        else:
            logger.warning(f"暂未支持的动作类型: {action_type}")

    def _handle_save_attachments(self, email: ParsedEmail, params: dict):
        if not email.attachments:
            logger.debug(f"邮件 [{email.subject}] 无附件，跳过保存附件动作")
            return

        dest_pattern = params.get("destination", self.config.storage.attachment_dir)
        allowed_exts = [ext.lower() for ext in params.get("allowed_extensions", [])]

        now = email.date or datetime.now()
        date_str = now.strftime("%Y%m%d")
        yyyy = now.strftime("%Y")
        mm = now.strftime("%m")
        dd = now.strftime("%d")

        # 格式化目标目录
        formatted_dest = dest_pattern.replace("{YYYY}", yyyy).replace("{MM}", mm).replace("{DD}", dd).replace("{date}", date_str)
        target_dir = Path(formatted_dest)
        target_dir.mkdir(parents=True, exist_ok=True)

        for att in email.attachments:
            ext = Path(att.filename).suffix.lower()
            if allowed_exts and ext not in allowed_exts:
                logger.debug(f"附件 {att.filename} 后缀不在允许列表 {allowed_exts} 中，跳过")
                continue

            # 处理 Windows 文件名重命名和特殊字符清理
            rename_pattern = params.get("rename_pattern")
            if rename_pattern:
                safe_sender = re.sub(r'[\\/*?:"<>|]', "_", email.sender_name or email.sender_email or "unknown")
                stem = Path(att.filename).stem
                final_name = (
                    rename_pattern
                    .replace("{date}", date_str)
                    .replace("{sender}", safe_sender)
                    .replace("{filename}", stem)
                    + ext
                )
            else:
                final_name = att.filename

            # 最终 Windows 文件名安全性过滤
            safe_final_name = re.sub(r'[\\/*?:"<>|]', "_", final_name)
            out_file = target_dir / safe_final_name

            # 写入附件
            out_file.write_bytes(att.data)
            logger.info(f"附件已成功保存: {out_file.resolve()} (大小: {len(att.data)} 字节)")

    def _handle_mark_read(self, email: ParsedEmail):
        if self.client and email.uid is not None:
            self.client.mark_as_read(email.uid)

    def _handle_move_folder(self, email: ParsedEmail, params: dict):
        target_folder = params.get("target_folder")
        if not target_folder:
            logger.warning("移动邮件失败: 未指定 target_folder 参数")
            return
        if self.client and email.uid is not None:
            self.client.move_email(email.uid, target_folder)
