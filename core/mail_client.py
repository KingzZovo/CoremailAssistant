"""Coremail IMAP/SMTP Client engine.
Supports IMAP fetching, GB18030/GBK/UTF-8 decoding, attachment caching,
inline image conversion (cid <-> local URI/base64), and SMTP rich text sending.
"""

import os
import re
import time
import uuid
import base64
import socket
import imaplib
import smtplib
import email
from urllib.parse import urlparse
from email.header import decode_header, make_header
from email.utils import getaddresses, formataddr, formatdate, make_msgid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
from typing import List, Dict, Any, Optional, Tuple


def decode_mime_str(value: Optional[str]) -> str:
    """安全解码 RFC2047 邮件头，兼容 Coremail 常见的 GB18030/GBK/UTF-8 编码"""
    if not value:
        return ""
    decoded_parts = []
    try:
        chunks = decode_header(value)
    except Exception:
        return str(value)

    for part, charset in chunks:
        if isinstance(part, bytes):
            enc = (charset or "utf-8").lower()
            if enc in ("gb2312", "gbk", "default", "x-gbk"):
                enc = "gb18030"
            try:
                decoded_parts.append(part.decode(enc, errors="replace"))
            except (LookupError, UnicodeDecodeError):
                for fallback_enc in ("gb18030", "utf-8", "latin1"):
                    try:
                        decoded_parts.append(part.decode(fallback_enc, errors="replace"))
                        break
                    except Exception:
                        pass
        else:
            decoded_parts.append(str(part))
    return "".join(decoded_parts).strip()


def parse_address_list(header_values: List[str]) -> List[Dict[str, str]]:
    """解析邮件地址列表并返回标准字典列表 [{'name': ..., 'email': ...}]"""
    if not header_values:
        return []
    decoded_headers = [decode_mime_str(h) for h in header_values if h]
    raw_pairs = getaddresses(decoded_headers)
    result = []
    seen = set()
    for name, addr in raw_pairs:
        clean_addr = addr.strip().lower()
        if clean_addr and "@" in clean_addr and clean_addr not in seen:
            seen.add(clean_addr)
            clean_name = decode_mime_str(name).strip(' "\'')
            result.append({
                "name": clean_name or clean_addr.split("@")[0],
                "email": addr.strip()
            })
    return result


def normalize_host_and_port(raw_host: str, default_port: int = 143) -> Tuple[str, int]:
    """
    清洗用户在设置中填写的服务器地址，防止因包含 http://、端口号或路径导致 Windows 报 Errno 11001。
    例如输入 'http://192.168.1.50:8080/coremail/' -> 返回 ('192.168.1.50', 8080)
    输入 'mail.corp.local:993' -> 返回 ('mail.corp.local', 993)
    输入 'mail.corp.local' -> 返回 ('mail.corp.local', default_port)
    """
    if not raw_host:
        return "", default_port
    s = raw_host.strip()
    if "://" not in s:
        s = "http://" + s
    try:
        parsed = urlparse(s)
        clean_host = (parsed.hostname or "").strip()
        port = parsed.port if parsed.port is not None else default_port
        return clean_host, port
    except Exception:
        m = re.match(r"^(?:https?://)?([^:/]+)(?::(\d+))?", raw_host.strip(), re.IGNORECASE)
        if m:
            clean_host = m.group(1).strip()
            port = int(m.group(2)) if m.group(2) else default_port
            return clean_host, port
        return raw_host.strip(), default_port


def probe_coremail_server_ports(raw_host: str) -> Dict[str, Any]:
    """
    针对内网/专有 Coremail 服务器一键探测实际开放的收发端口（解决内网未开 SSL 993/465 而是开 143/25 的情况）
    """
    clean_host, _ = normalize_host_and_port(raw_host, 143)
    if not clean_host:
        return {"ok": False, "msg": "服务器地址不能为空，请填写论客客户端中的服务器 IP 或域名。"}

    # 第一步：验证 DNS / IP 解析（捕获 Errno 11001）
    try:
        resolved_ip = socket.gethostbyname(clean_host)
    except socket.gaierror as e:
        err_no = getattr(e, "errno", 11001)
        return {
            "ok": False,
            "host": clean_host,
            "msg": (
                f"无法解析服务器地址「{clean_host}」(Errno {err_no})。\n"
                f"原因：当前内网 DNS 无法识别该域名，或地址格式不正确。\n"
                f"建议：请打开论客客户端【设置 -> 帐号管理】查看真实服务器地址，或直接填写邮件服务器的内网 IP 地址。"
            )
        }

    def is_port_open(port: int) -> bool:
        try:
            with socket.create_connection((resolved_ip, port), timeout=2.0):
                return True
        except Exception:
            return False

    # 第二步：探测 IMAP 端口（优先 993 SSL，其次 143 明文）
    if is_port_open(993):
        imap_port, imap_ssl = 993, True
    elif is_port_open(143):
        imap_port, imap_ssl = 143, False
    else:
        imap_port, imap_ssl = 143, False

    # 第三步：探测 SMTP 端口（优先 465 SSL，其次 25 明文，再次 587）
    if is_port_open(465):
        smtp_port, smtp_ssl = 465, True
    elif is_port_open(25):
        smtp_port, smtp_ssl = 25, False
    elif is_port_open(587):
        smtp_port, smtp_ssl = 587, False
    else:
        smtp_port, smtp_ssl = 25, False

    ssl_imap_text = "开启" if imap_ssl else "关闭"
    ssl_smtp_text = "开启" if smtp_ssl else "关闭"
    return {
        "ok": True,
        "host": clean_host,
        "resolved_ip": resolved_ip,
        "imap_port": imap_port,
        "imap_ssl": imap_ssl,
        "smtp_port": smtp_port,
        "smtp_ssl": smtp_ssl,
        "msg": f"探测成功 (解析到 IP: {resolved_ip})：\n推荐 IMAP 端口 {imap_port} (SSL={ssl_imap_text})，\nSMTP 端口 {smtp_port} (SSL={ssl_smtp_text})"
    }


auto_detect_server = probe_coremail_server_ports


class CoremailClient:
    """Coremail 论客邮箱 IMAP/SMTP 客户端封装（支持富文本 HTML 及内联图片发送）"""

    normalize_host_and_port = staticmethod(normalize_host_and_port)
    probe_coremail_server_ports = staticmethod(probe_coremail_server_ports)
    auto_detect_server = staticmethod(probe_coremail_server_ports)

    def __init__(self, config: Dict[str, Any], attachment_root: str = "data/attachments"):
        self.protocol_mode = config.get("protocol_mode", "coremail")
        coremail_srv = config.get("coremail_server", "").strip()

        # 如果采用 coremail 单地址模式且填写了 coremail_server，则优先将其作为 IMAP 与 SMTP 主机
        raw_imap = coremail_srv if (self.protocol_mode == "coremail" and coremail_srv) else config.get("imap_host", "").strip()
        raw_smtp = coremail_srv if (self.protocol_mode == "coremail" and coremail_srv) else config.get("smtp_host", "").strip()

        default_imap_port = int(config.get("imap_port", 993) or 993)
        default_smtp_port = int(config.get("smtp_port", 465) or 465)

        self.imap_host, self.imap_port = normalize_host_and_port(raw_imap, default_imap_port)
        self.smtp_host, self.smtp_port = normalize_host_and_port(raw_smtp, default_smtp_port)

        self.imap_ssl = str(config.get("imap_ssl", "1")).lower() in ("1", "true", "yes")
        self.smtp_ssl = str(config.get("smtp_ssl", "1")).lower() in ("1", "true", "yes")

        self.email_account = config.get("email_account", "").strip()
        self.email_password = config.get("email_password", "")
        self.sender_display_name = config.get("sender_display_name", "").strip()
        self.attachment_root = attachment_root
        os.makedirs(self.attachment_root, exist_ok=True)

    def _connect_imap(self) -> imaplib.IMAP4:
        """建立并登录 IMAP 连接（带清洗与自动降级回退）"""
        clean_host, _ = normalize_host_and_port(self.imap_host, self.imap_port)
        if not clean_host:
            raise ValueError("IMAP 服务器主机名为空")

        try:
            if self.imap_ssl:
                conn = imaplib.IMAP4_SSL(clean_host, self.imap_port, timeout=15)
            else:
                conn = imaplib.IMAP4(clean_host, self.imap_port, timeout=15)
            conn.login(self.email_account, self.email_password)
            return conn
        except (socket.gaierror, Exception) as primary_err:
            if isinstance(primary_err, socket.gaierror):
                err_code = getattr(primary_err, 'errno', 11001)
                raise socket.gaierror(
                    err_code,
                    f"无法解析服务器域名 '{clean_host}' (Errno {err_code})，请检查地址拼写或直接填写内网 IP 地址"
                ) from primary_err

            # 在 coremail 模式下若 993 SSL 失败，自动尝试回退降级到 143 明文端口
            if self.protocol_mode == "coremail" and self.imap_ssl:
                try:
                    conn = imaplib.IMAP4(clean_host, 143, timeout=10)
                    conn.login(self.email_account, self.email_password)
                    self.imap_port = 143
                    self.imap_ssl = False
                    return conn
                except Exception:
                    pass
            raise primary_err

    def test_connection(self) -> Dict[str, Any]:
        """测试 IMAP 和 SMTP 连接与凭据有效性（友好的中文报错与降级保护）"""
        if not self.email_account or not self.email_password:
            return {"ok": False, "msg": "邮箱账号或密码未填写"}
        if not self.imap_host and not self.smtp_host:
            return {"ok": False, "msg": "服务器地址未填写"}

        try:
            # 1. 测试 IMAP 连接
            imap_conn = self._connect_imap()
            imap_conn.select("INBOX", readonly=True)
            imap_conn.logout()

            # 2. 测试 SMTP 连接
            clean_smtp, _ = normalize_host_and_port(self.smtp_host, self.smtp_port)
            smtp_conn = None
            try:
                if self.smtp_ssl:
                    smtp_conn = smtplib.SMTP_SSL(clean_smtp, self.smtp_port, timeout=15)
                else:
                    smtp_conn = smtplib.SMTP(clean_smtp, self.smtp_port, timeout=15)
                    smtp_conn.ehlo()
                smtp_conn.login(self.email_account, self.email_password)
            except Exception as smtp_err:
                # 在 coremail 模式下尝试回退到 25 端口
                if self.protocol_mode == "coremail" and self.smtp_ssl:
                    try:
                        smtp_conn = smtplib.SMTP(clean_smtp, 25, timeout=10)
                        smtp_conn.ehlo()
                        smtp_conn.login(self.email_account, self.email_password)
                        self.smtp_port = 25
                        self.smtp_ssl = False
                    except Exception:
                        raise smtp_err
                else:
                    raise smtp_err
            finally:
                if smtp_conn:
                    try:
                        smtp_conn.quit()
                    except Exception:
                        pass

            return {"ok": True, "msg": "Coremail 论客服务器连接验证成功！收发服务均正常。"}
        except socket.gaierror as e:
            err_code = getattr(e, 'errno', 11001)
            return {
                "ok": False,
                "msg": f"解析服务器地址失败 (Errno {err_code})：当前网络无法解析该域名，请检查拼写或直接输入论客服务器的内网 IP 地址。"
            }
        except Exception as e:
            err_str = str(e)
            if "11001" in err_str:
                return {
                    "ok": False,
                    "msg": "连接失败 (Errno 11001)：主机名无法解析，请检查服务器地址是否包含 http:// 或多余字符，建议直接填写 IP 地址。"
                }
            return {"ok": False, "msg": f"连接失败: {err_str}"}

    def fetch_new_emails(self, existing_uids: set, max_fetch: int = 30) -> List[Dict[str, Any]]:
        """从收件箱拉取尚未入库的邮件列表"""
        new_emails = []
        if not self.email_account or not self.email_password:
            return []

        conn = self._connect_imap()
        try:
            conn.select("INBOX", readonly=True)
            typ, data = conn.uid("search", None, "ALL")
            if typ != "OK" or not data or not data[0]:
                return []

            all_uids = [u.decode("utf-8") for u in data[0].split()]
            # 取最近的 max_fetch 封未记录 UID
            candidate_uids = [u for u in all_uids[-max_fetch:] if u not in existing_uids]

            for uid in candidate_uids:
                try:
                    typ, msg_data = conn.uid("fetch", uid, "(BODY.PEEK[])")
                    if typ != "OK" or not msg_data or not msg_data[0]:
                        continue
                    raw_bytes = msg_data[0][1]
                    if not isinstance(raw_bytes, bytes):
                        continue
                    parsed = self._parse_raw_email(uid, raw_bytes)
                    if parsed:
                        new_emails.append(parsed)
                except Exception:
                    continue
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        return new_emails

    def _parse_raw_email(self, uid: str, raw_bytes: bytes) -> Optional[Dict[str, Any]]:
        """解析原始 RFC822 字节流，并将附件和内联图片保存到本地磁盘"""
        msg = email.message_from_bytes(raw_bytes)
        subject = decode_mime_str(msg.get("Subject", "(无主题)"))
        message_id = decode_mime_str(msg.get("Message-ID", ""))
        date_str = decode_mime_str(msg.get("Date", ""))

        from_list = parse_address_list(msg.get_all("From", []))
        sender_name = from_list[0]["name"] if from_list else ""
        sender_email = from_list[0]["email"] if from_list else ""

        to_list = parse_address_list(msg.get_all("To", []))
        cc_list = parse_address_list(msg.get_all("Cc", []))

        body_text_parts = []
        body_html_parts = []
        attachments = []
        cid_map: Dict[str, str] = {}

        uid_attach_dir = os.path.join(self.attachment_root, str(uid))

        for part in msg.walk():
            content_type = part.get_content_type()
            content_disp = str(part.get("Content-Disposition") or "")
            content_id = str(part.get("Content-ID") or "").strip("<> ")
            filename = part.get_filename()

            # 检测普通附件或包含 Content-ID 的正文内联图片
            if filename or "attachment" in content_disp.lower() or (content_type.startswith("image/") and content_id):
                decoded_fname = decode_mime_str(filename) if filename else f"inline_{content_id or uuid.uuid4().hex[:6]}.png"
                # 清除 Windows 非法文件名字符
                safe_fname = re.sub(r'[\\/:*?"<>|]', "_", decoded_fname)
                os.makedirs(uid_attach_dir, exist_ok=True)
                file_path = os.path.abspath(os.path.join(uid_attach_dir, safe_fname))

                payload = part.get_payload(decode=True)
                if payload is not None:
                    with open(file_path, "wb") as f:
                        f.write(payload)

                    if content_id and "attachment" not in content_disp.lower():
                        cid_map[content_id] = file_path
                    else:
                        attachments.append({
                            "filename": safe_fname,
                            "filepath": file_path,
                            "size": len(payload)
                        })
                continue

            payload = part.get_payload(decode=True)
            if not payload:
                continue

            charset = part.get_content_charset() or "utf-8"
            if charset.lower() in ("gb2312", "gbk", "default"):
                charset = "gb18030"
            try:
                text_content = payload.decode(charset, errors="replace")
            except LookupError:
                text_content = payload.decode("utf-8", errors="replace")

            if content_type == "text/plain":
                body_text_parts.append(text_content)
            elif content_type == "text/html":
                body_html_parts.append(text_content)

        body_text = "\n".join(body_text_parts).strip()
        body_html = "\n".join(body_html_parts).strip()

        # 将原邮件 HTML 中的 cid: 内联图片替换为本地文件 URI 以便富文本编辑器直接显示
        for cid_key, local_img_path in cid_map.items():
            file_uri = "file:///" + local_img_path.replace("\\", "/")
            body_html = body_html.replace(f"cid:{cid_key}", file_uri)

        if not body_text and body_html:
            body_text = re.sub(r"<[^>]+>", " ", body_html)
            body_text = re.sub(r"\s+", " ", body_text).strip()

        return {
            "uid": str(uid),
            "message_id": message_id,
            "subject": subject,
            "sender_name": sender_name,
            "sender_email": sender_email,
            "to_list": to_list,
            "cc_list": cc_list,
            "date_str": date_str,
            "body_text": body_text,
            "body_html": body_html,
            "attachments": attachments,
        }

    @staticmethod
    def _extract_inline_images_from_html(html_body: str) -> Tuple[str, List[Tuple[str, bytes, str]]]:
        """
        将富文本编辑器生成的 data:image/...;base64 或 file:/// 本地图片转为标准邮件 cid: 内联图片，
        确保收件人在 Coremail 论客客户端中能正常看到正文内嵌图片。
        """
        inline_images: List[Tuple[str, bytes, str]] = []

        # 1. 处理 data:image/png;base64,...
        def repl_base64(match):
            img_ext = match.group(1).lower() or "png"
            b64_data = match.group(2)
            try:
                raw = base64.b64decode(b64_data)
                cid = f"img_{uuid.uuid4().hex[:10]}"
                inline_images.append((cid, raw, img_ext))
                return f'src="cid:{cid}"'
            except Exception:
                return match.group(0)

        processed_html = re.sub(
            r'src=["\']data:image/([a-zA-Z0-9+]+);base64,([^"\']+)["\']',
            repl_base64,
            html_body
        )

        # 2. 处理 file:/// 本地图片路径
        def repl_file(match):
            raw_path = match.group(1)
            local_path = raw_path.replace("file:///", "").replace("/", os.sep)
            if os.path.isfile(local_path):
                try:
                    with open(local_path, "rb") as f:
                        raw = f.read()
                    ext = os.path.splitext(local_path)[1].lstrip(".").lower() or "png"
                    cid = f"img_{uuid.uuid4().hex[:10]}"
                    inline_images.append((cid, raw, ext))
                    return f'src="cid:{cid}"'
                except Exception:
                    pass
            return match.group(0)

        processed_html = re.sub(r'src=["\'](file:///[^"\']+)["\']', repl_file, processed_html)
        return processed_html, inline_images

    def send_email(
        self,
        to_addrs: List[str],
        cc_addrs: List[str],
        subject: str,
        html_body: str,
        plain_body: str,
        attachment_paths: List[str],
        save_to_sent: bool = True
    ) -> None:
        """发送富文本邮件（支持新建改写邮件与标准转发邮件，支持正文内联图片与文件附件）"""
        if not self.email_account or not self.email_password:
            raise ValueError("未配置发信邮箱账号或密码")

        msg = MIMEMultipart("mixed")
        display_name = self.sender_display_name or self.email_account.split("@")[0]
        from_header = formataddr((str(make_header([(display_name, "utf-8")])), self.email_account))
        msg["From"] = from_header
        msg["To"] = ", ".join(to_addrs)
        if cc_addrs:
            msg["Cc"] = ", ".join(cc_addrs)
        msg["Subject"] = str(make_header([(subject, "utf-8")]))
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()

        processed_html, inline_images = self._extract_inline_images_from_html(html_body or "")

        related_part = MIMEMultipart("related")
        alt_part = MIMEMultipart("alternative")
        alt_part.attach(MIMEText(plain_body or "", "plain", "utf-8"))
        alt_part.attach(MIMEText(processed_html or "", "html", "utf-8"))
        related_part.attach(alt_part)

        for cid, img_bytes, subtype in inline_images:
            img_part = MIMEImage(img_bytes, _subtype=subtype)
            img_part.add_header("Content-ID", f"<{cid}>")
            img_part.add_header("Content-Disposition", "inline", filename=f"{cid}.{subtype}")
            related_part.attach(img_part)

        msg.attach(related_part)

        # 挂载文件附件
        for path in attachment_paths:
            if not path or not os.path.isfile(path):
                continue
            fname = os.path.basename(path)
            with open(path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", fname))
            msg.attach(part)

        all_recipients = list(dict.fromkeys([a.strip() for a in (to_addrs + cc_addrs) if a.strip()]))
        raw_message = msg.as_bytes()

        # SMTP 发送
        clean_smtp, _ = normalize_host_and_port(self.smtp_host, self.smtp_port)
        smtp = None
        try:
            if self.smtp_ssl:
                smtp = smtplib.SMTP_SSL(clean_smtp, self.smtp_port, timeout=20)
            else:
                smtp = smtplib.SMTP(clean_smtp, self.smtp_port, timeout=20)
                smtp.ehlo()
            smtp.login(self.email_account, self.email_password)
            smtp.sendmail(self.email_account, all_recipients, raw_message)
        except Exception as primary_smtp_err:
            if self.protocol_mode == "coremail" and self.smtp_ssl:
                try:
                    smtp = smtplib.SMTP(clean_smtp, 25, timeout=15)
                    smtp.ehlo()
                    smtp.login(self.email_account, self.email_password)
                    smtp.sendmail(self.email_account, all_recipients, raw_message)
                    self.smtp_port = 25
                    self.smtp_ssl = False
                except Exception:
                    raise primary_smtp_err
            else:
                raise primary_smtp_err
        finally:
            if smtp:
                try:
                    smtp.quit()
                except Exception:
                    pass

        # 写入已发送文件夹
        if save_to_sent:
            try:
                imap = self._connect_imap()
                sent_folders = ('"Sent Messages"', '"Sent"', '"已发送"', '"已发送邮件"', '"&XfJT0ZAB-"')
                for folder in sent_folders:
                    try:
                        typ, _ = imap.append(folder, "\\Seen", imaplib.Time2Internaldate(time.time()), raw_message)
                        if typ == "OK":
                            break
                    except Exception:
                        continue
                imap.logout()
            except Exception:
                pass

    def mark_email_read(self, uid: str) -> None:
        """标记邮件为已读"""
        if not self.email_account or not self.email_password:
            return
        conn = self._connect_imap()
        try:
            conn.select("INBOX")
            conn.uid("store", str(uid), "+FLAGS", "(\\Seen)")
        finally:
            try:
                conn.logout()
            except Exception:
                pass
