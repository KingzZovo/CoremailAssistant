"""Email parser utility for decoding headers, body, and attachments."""

from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from email.header import decode_header
from email.parser import BytesParser
from typing import List, Optional, Tuple
import re


@dataclass
class EmailAttachment:
    filename: str
    content_type: str
    size: int
    data: bytes


@dataclass
class ParsedEmail:
    msg_id: str
    uid: Optional[int] = None
    subject: str = ""
    sender: str = ""
    sender_name: str = ""
    sender_email: str = ""
    recipients: List[str] = field(default_factory=list)
    date: Optional[datetime] = None
    date_str: str = ""
    body_text: str = ""
    body_html: str = ""
    attachments: List[EmailAttachment] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)


class MailParser:
    """Coremail 邮件解析器，专门优化了中文常见编码 (GBK/GB2312/GB18030/UTF-8) 兼容性"""

    @staticmethod
    def decode_str(header_str: Optional[str]) -> str:
        """解码邮件标头（如 Subject, From 等）"""
        if not header_str:
            return ""

        decoded_chunks = []
        try:
            chunks = decode_header(header_str)
            for chunk, encoding in chunks:
                if isinstance(chunk, bytes):
                    if encoding:
                        try:
                            decoded_chunks.append(chunk.decode(encoding, errors="replace"))
                        except (LookupError, UnicodeDecodeError):
                            # 回退常见中文编码
                            decoded_chunks.append(MailParser._fallback_decode_bytes(chunk))
                    else:
                        decoded_chunks.append(MailParser._fallback_decode_bytes(chunk))
                else:
                    decoded_chunks.append(str(chunk))
            return "".join(decoded_chunks).strip()
        except Exception:
            return str(header_str)

    @staticmethod
    def _fallback_decode_bytes(data: bytes) -> str:
        for enc in ("utf-8", "gb18030", "gbk", "gb2312", "latin1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    @classmethod
    def parse_bytes(cls, raw_bytes: bytes, uid: Optional[int] = None) -> ParsedEmail:
        """解析原始邮件字节流为 ParsedEmail 结构体"""
        msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)

        # 标头解析
        subject = cls.decode_str(msg.get("subject", ""))
        sender_raw = cls.decode_str(msg.get("from", ""))
        msg_id = str(msg.get("message-id", "")).strip("<>")

        sender_email = ""
        sender_name = ""
        match = re.search(r"[\w\.-]+@[\w\.-]+", sender_raw)
        if match:
            sender_email = match.group(0)
            sender_name = sender_raw.replace(f"<{sender_email}>", "").replace(sender_email, "").strip(" \"'")
        else:
            sender_email = sender_raw
            sender_name = sender_raw

        # 收件人
        to_raw = cls.decode_str(msg.get("to", ""))
        recipients = [to_raw] if to_raw else []

        # 日期
        date_obj = msg.get("date")
        date_val = None
        date_str = ""
        if date_obj:
            date_str = str(date_obj)
            try:
                date_val = msg.get("date").datetime
            except Exception:
                pass

        # 正文及附件解析
        body_text = ""
        body_html = ""
        attachments: List[EmailAttachment] = []

        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition", ""))
                content_type = part.get_content_type()
                filename = part.get_filename()

                if filename:
                    filename = cls.decode_str(filename)
                    # 避免 Windows 路径非法字符
                    safe_filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
                    payload = part.get_payload(decode=True)
                    if payload:
                        attachments.append(EmailAttachment(
                            filename=safe_filename,
                            content_type=content_type,
                            size=len(payload),
                            data=payload
                        ))
                else:
                    if "attachment" in content_disposition:
                        continue
                    if content_type == "text/plain" and not body_text:
                        body_text = part.get_content() or ""
                    elif content_type == "text/html" and not body_html:
                        body_html = part.get_content() or ""
        else:
            content_type = msg.get_content_type()
            if content_type == "text/plain":
                body_text = msg.get_content() or ""
            elif content_type == "text/html":
                body_html = msg.get_content() or ""

        return ParsedEmail(
            msg_id=msg_id,
            uid=uid,
            subject=subject,
            sender=sender_raw,
            sender_name=sender_name,
            sender_email=sender_email,
            recipients=recipients,
            date=date_val,
            date_str=date_str,
            body_text=body_text,
            body_html=body_html,
            attachments=attachments
        )
