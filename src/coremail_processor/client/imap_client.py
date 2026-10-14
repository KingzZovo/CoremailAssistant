"""Coremail IMAP client implementation."""

from typing import List, Tuple, Optional
from imapclient import IMAPClient
from loguru import logger
from ..config import MailServerConfig


class CoremailIMAPClient:
    """Coremail 邮箱 IMAP 客户端封装"""

    def __init__(self, config: MailServerConfig):
        self.config = config
        self.client: Optional[IMAPClient] = None

    def connect(self) -> "CoremailIMAPClient":
        """建立连接并完成用户鉴权登录"""
        logger.info(f"正在连接论客邮箱服务器: {self.config.imap_host}:{self.config.imap_port} (SSL={self.config.use_ssl})")
        self.client = IMAPClient(
            host=self.config.imap_host,
            port=self.config.imap_port,
            ssl=self.config.use_ssl
        )
        self.client.login(self.config.username, self.config.password)
        logger.info(f"论客邮箱登录成功: {self.config.username}")
        return self

    def disconnect(self):
        """安全断开与邮件服务器的连接"""
        if self.client:
            try:
                self.client.logout()
                logger.info("已安全断开论客邮箱连接")
            except Exception as e:
                logger.warning(f"断开连接时发生异常: {e}")
            finally:
                self.client = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def select_folder(self, folder: Optional[str] = None):
        """切换工作邮件夹"""
        target = folder or self.config.folder
        if not self.client:
            raise RuntimeError("客户端尚未连接，请先执行 connect()")
        self.client.select_folder(target)
        logger.debug(f"已选中邮箱文件夹: {target}")

    def fetch_unread_uids(self, limit: Optional[int] = None) -> List[int]:
        """检索未读邮件 UID 列表"""
        if not self.client:
            raise RuntimeError("客户端尚未连接")
        uids = self.client.search(["UNSEEN"])
        if limit and len(uids) > limit:
            uids = uids[:limit]
        logger.info(f"检索到 {len(uids)} 封未读邮件")
        return uids

    def fetch_email_raw(self, uid: int) -> bytes:
        """根据 UID 获取邮件原始 RFC822 字节流"""
        if not self.client:
            raise RuntimeError("客户端尚未连接")
        response = self.client.fetch([uid], ["RFC822"])
        if uid in response and b"RFC822" in response[uid]:
            return response[uid][b"RFC822"]
        raise ValueError(f"未找到 UID 为 {uid} 的邮件内容")

    def mark_as_read(self, uid: int):
        """将邮件标记为已读"""
        if not self.client:
            raise RuntimeError("客户端尚未连接")
        self.client.add_flags(uid, [b"\\Seen"])
        logger.debug(f"邮件 UID {uid} 已标记为已读")

    def move_email(self, uid: int, target_folder: str):
        """将邮件移动到指定邮件夹 (兼顾支持 MOVE 与 COPY+DELETE)"""
        if not self.client:
            raise RuntimeError("客户端尚未连接")
        try:
            self.client.move(uid, target_folder)
            logger.info(f"邮件 UID {uid} 已移动至文件夹: {target_folder}")
        except Exception:
            # 兼容不支持 MOVE 扩展的服务器
            self.client.copy(uid, target_folder)
            self.client.add_flags(uid, [b"\\Deleted"])
            self.client.expunge()
            logger.info(f"邮件 UID {uid} 已通过复制+清理移动至: {target_folder}")
