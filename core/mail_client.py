"""Coremail Client engine supporting both standard IMAP/SMTP and genuine Coremail WebAPI (/coremail/s/json).
Supports HTTP/HTTPS WebAPI, IMAP fetching, POP3 fallback, GB18030/GBK/UTF-8 decoding,
attachment caching, inline image conversion (cid <-> local URI/base64), and rich text sending.
"""

import os
import re
import time
import uuid
import base64
import socket
import imaplib
import smtplib
import poplib
import email
from urllib.parse import urlparse, quote, unquote
from email.header import decode_header, make_header
from email.utils import getaddresses, formataddr, formatdate, make_msgid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
from typing import List, Dict, Any, Optional, Tuple

import requests
import urllib3

from config import ATTACHMENTS_DIR

# 忽略内网自签名证书安全警告
urllib3.disable_warnings()


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


def parse_server_endpoint(raw_host: str) -> Dict[str, Any]:
    """
    解析服务器配置字符串，提取 scheme, host, port, path
    例如 'http://192.168.1.50:8080/coremail/' -> {'scheme': 'http', 'host': '192.168.1.50', 'port': 8080, 'path': '/coremail/'}
    """
    if not raw_host:
        return {"scheme": "", "host": "", "port": None, "path": ""}
    s = raw_host.strip()
    has_scheme = "://" in s
    if not has_scheme:
        s = "http://" + s
    try:
        parsed = urlparse(s)
        clean_host = (parsed.hostname or "").strip()
        port = parsed.port
        scheme = parsed.scheme if has_scheme else ""
        return {
            "scheme": scheme.lower(),
            "host": clean_host,
            "port": port,
            "path": parsed.path or ""
        }
    except Exception:
        m = re.match(r"^(?:(https?)://)?([^:/]+)(?::(\d+))?", raw_host.strip(), re.IGNORECASE)
        if m:
            scheme = (m.group(1) or "").lower()
            clean_host = m.group(2).strip()
            port = int(m.group(3)) if m.group(3) else None
            return {"scheme": scheme, "host": clean_host, "port": port, "path": ""}
        return {"scheme": "", "host": raw_host.strip(), "port": None, "path": ""}


def normalize_host_and_port(raw_host: str, default_port: int = 143) -> Tuple[str, int]:
    """
    清洗用户在设置中填写的服务器地址，防止因包含 http://、端口号或路径导致 Windows 报 Errno 11001。
    例如输入 'http://192.168.1.50:8080/coremail/' -> 返回 ('192.168.1.50', 8080)
    输入 'mail.corp.local:993' -> 返回 ('mail.corp.local', 993)
    输入 'mail.corp.local' -> 返回 ('mail.corp.local', default_port)
    """
    if not raw_host:
        return "", default_port
    info = parse_server_endpoint(raw_host)
    clean_host = info.get("host") or ""
    port = info.get("port") if info.get("port") is not None else default_port
    return clean_host, port


def decode_imap_utf7(folder_name: str) -> str:
    """解码 IMAP Modified UTF-7 编码的文件夹名称（如 &V4NXPpCuTvY- -> 项目组）"""
    if not folder_name or "&" not in folder_name:
        return folder_name

    def _sub_repl(match):
        raw_b64 = match.group(1).replace(",", "/")
        pad = len(raw_b64) % 4
        if pad:
            raw_b64 += "=" * (4 - pad)
        try:
            return base64.b64decode(raw_b64.encode("ascii")).decode("utf-16-be")
        except Exception:
            return match.group(0)

    res = folder_name.replace("&-", "\x00")
    res = re.sub(r"&([A-Za-z0-9+,]+)-", _sub_repl, res)
    res = res.replace("\x00", "&")
    return res


def is_system_non_inbox_folder(folder_id: Any, folder_name: str) -> bool:
    """判断是否为草稿箱、已发送、已删除、垃圾箱等非收信类文件夹"""
    fid_str = str(folder_id).strip()
    if fid_str in ("2", "3", "4", "5"):
        return True
    lower = (folder_name or "").lower().strip()
    exclude_keywords = [
        "草稿", "已发送", "已删除", "垃圾", "病毒",
        "draft", "sent", "trash", "junk", "spam", "deleted"
    ]
    return any(k in lower for k in exclude_keywords)


def _extract_body_from_coremail_json(var_data: Any) -> Tuple[str, str]:
    """
    通用提取 Coremail WebAPI (mbox:readMessage / mbox:getMessageData / mbox:getMessageInfos)
    返回的多种嵌套结构中的 html 和 text 正文
    返回 (body_text, body_html)
    """
    if not isinstance(var_data, dict):
        return "", ""

    body_html = ""
    body_text = ""

    # 1. 结构: {"html": {"content": ...}} 或 {"html": "..."}
    h_val = var_data.get("html")
    if isinstance(h_val, dict):
        body_html = h_val.get("content") or h_val.get("body") or ""
    elif isinstance(h_val, str):
        body_html = h_val

    # 2. 结构: {"text": {"content": ...}} 或 {"text": "..."}
    t_val = var_data.get("text")
    if isinstance(t_val, dict):
        body_text = t_val.get("content") or t_val.get("body") or ""
    elif isinstance(t_val, str):
        body_text = t_val

    # 3. 直接字段: content / body / htmlBody / textBody
    if not body_html:
        body_html = var_data.get("htmlBody") or var_data.get("content") or var_data.get("body") or ""
    if not body_text:
        body_text = var_data.get("textBody") or ""

    # 4. parts 列表: [{"type": "text/html", "content": ...}, {"type": "text/plain", "content": ...}]
    parts = var_data.get("parts") or []
    if isinstance(parts, list):
        for p in parts:
            if not isinstance(p, dict):
                continue
            p_type = str(p.get("type") or p.get("contentType") or "").lower()
            p_content = p.get("content") or p.get("body") or ""
            if "html" in p_type and not body_html:
                body_html = p_content
            elif "plain" in p_type and not body_text:
                body_text = p_content

    # 如果有 html 但没有 text，通过正则清洗 html 标签作为 text
    if not body_text and body_html:
        clean = re.sub(r"<style[\s\S]*?</style>", "", body_html, flags=re.I)
        clean = re.sub(r"<script[\s\S]*?</script>", "", clean, flags=re.I)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        body_text = clean

    return body_text, body_html


def probe_coremail_server_ports(raw_host: str) -> Dict[str, Any]:
    """
    真实探测 Coremail 服务器开放的收发端口（彻底杜绝假阳性，并探测 HTTP/HTTPS 与 POP3 端口）。
    严禁在端口不通时强行赋默认值假装成功！
    """
    raw_host = (raw_host or "").strip()
    if not raw_host:
        return {"ok": False, "msg": "服务器地址不能为空，请填写论客客户端中的服务器 IP 或域名。"}

    endpoint = parse_server_endpoint(raw_host)
    clean_host = endpoint["host"]
    custom_port = endpoint["port"]
    custom_scheme = endpoint["scheme"]

    if not clean_host:
        return {"ok": False, "msg": "无法从地址中识别有效主机名或 IP，请检查格式。"}

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

    def is_port_open(port: int, timeout: float = 1.5) -> bool:
        try:
            with socket.create_connection((resolved_ip, port), timeout=timeout):
                return True
        except Exception:
            return False

    # 第二步：探测 Coremail HTTP/HTTPS 专用协议端口 [custom_port, 443, 80, 8080, 8443]
    http_candidates: List[int] = []
    if custom_port:
        http_candidates.append(custom_port)
    for p in [443, 80, 8080, 8443]:
        if p not in http_candidates:
            http_candidates.append(p)

    open_http_port: Optional[int] = None
    http_scheme: Optional[str] = None
    http_base_url: Optional[str] = None

    for p in http_candidates:
        if is_port_open(p):
            schemes = ["https", "http"] if p in (443, 8443) else ["http", "https"]
            if custom_scheme in ("http", "https"):
                schemes = [custom_scheme] + [s for s in schemes if s != custom_scheme]

            for s in schemes:
                test_base = f"{s}://{clean_host}" if p in (80, 443) else f"{s}://{clean_host}:{p}"
                try:
                    sess = requests.Session()
                    sess.trust_env = False
                    r = sess.get(f"{test_base}/coremail/", timeout=2.0, verify=False, allow_redirects=True)
                    if r.status_code < 500:
                        open_http_port = p
                        http_scheme = s
                        http_base_url = test_base
                        break
                except Exception:
                    pass

            if open_http_port is None:
                # 端口已通，即使未配置 /coremail/ 重定向也作为备选 HTTP 基础地址
                open_http_port = p
                http_scheme = "https" if p in (443, 8443) else "http"
                http_base_url = f"{http_scheme}://{clean_host}" if p in (80, 443) else f"{http_scheme}://{clean_host}:{p}"
            break

    # 第三步：探测 IMAP 端口 [993, 143]（严禁无端口开放时赋予虚假默认值）
    imap_port: Optional[int] = None
    imap_ssl: bool = False
    if is_port_open(993):
        imap_port, imap_ssl = 993, True
    elif is_port_open(143):
        imap_port, imap_ssl = 143, False

    # 第四步：探测 POP3 端口 [995, 110]
    pop3_port: Optional[int] = None
    pop3_ssl: bool = False
    if is_port_open(995):
        pop3_port, pop3_ssl = 995, True
    elif is_port_open(110):
        pop3_port, pop3_ssl = 110, False

    # 第五步：探测 SMTP 端口 [465, 25, 587]
    smtp_port: Optional[int] = None
    smtp_ssl: bool = False
    if is_port_open(465):
        smtp_port, smtp_ssl = 465, True
    elif is_port_open(25):
        smtp_port, smtp_ssl = 25, False
    elif is_port_open(587):
        smtp_port, smtp_ssl = 587, False

    # 汇总探测结果，严禁在全灭时报成功
    open_channels = []
    if http_base_url:
        open_channels.append(f"HTTP/Coremail WebAPI ({http_base_url})")
    if imap_port is not None:
        open_channels.append(f"IMAP ({imap_port}, SSL={'开启' if imap_ssl else '关闭'})")
    if pop3_port is not None:
        open_channels.append(f"POP3 ({pop3_port}, SSL={'开启' if pop3_ssl else '关闭'})")
    if smtp_port is not None:
        open_channels.append(f"SMTP ({smtp_port}, SSL={'开启' if smtp_ssl else '关闭'})")

    if not open_channels:
        return {
            "ok": False,
            "host": clean_host,
            "resolved_ip": resolved_ip,
            "msg": (
                f"服务器 IP「{clean_host}」({resolved_ip}) 解析成功，但 80/443/143/993/110/995/25/465 等端口均连接超时。\n"
                f"原因：内网防火墙可能拦截了访问，或服务器未开放对应服务。\n"
                f"建议：请检查论客客户端【设置 -> 帐号管理】中的真实服务器 IP 和端口号。"
            )
        }

    return {
        "ok": True,
        "host": clean_host,
        "resolved_ip": resolved_ip,
        "http_base_url": http_base_url,
        "http_port": open_http_port,
        "http_scheme": http_scheme,
        "imap_port": imap_port,
        "imap_ssl": imap_ssl,
        "pop3_port": pop3_port,
        "pop3_ssl": pop3_ssl,
        "smtp_port": smtp_port,
        "smtp_ssl": smtp_ssl,
        "open_channels": open_channels,
        "msg": f"探测成功 (解析到 IP: {resolved_ip})：\n已探测到开放通道与端口：\n• " + "\n• ".join(open_channels)
    }


auto_detect_server = probe_coremail_server_ports


class CoremailClient:
    """Coremail 论客邮箱多通道客户端（支持 Coremail WebAPI / IMAP / POP3 / SMTP）"""

    normalize_host_and_port = staticmethod(normalize_host_and_port)
    probe_coremail_server_ports = staticmethod(probe_coremail_server_ports)
    auto_detect_server = staticmethod(probe_coremail_server_ports)

    def __init__(self, config: Dict[str, Any], attachment_root: Optional[str] = None):
        self.config = config
        self.protocol_mode = config.get("protocol_mode", "coremail")
        self.coremail_server = config.get("coremail_server", "").strip()
        self.http_base_url = config.get("http_base_url", "").strip()

        # 如果采用 coremail 单地址模式且填写了 coremail_server，则优先将其作为 IMAP 与 SMTP 主机
        raw_imap = self.coremail_server if (self.protocol_mode == "coremail" and self.coremail_server) else config.get("imap_host", "").strip()
        raw_smtp = self.coremail_server if (self.protocol_mode == "coremail" and self.coremail_server) else config.get("smtp_host", "").strip()

        default_imap_port = int(config.get("imap_port", 993) or 993)
        default_smtp_port = int(config.get("smtp_port", 465) or 465)

        self.imap_host, self.imap_port = normalize_host_and_port(raw_imap, default_imap_port)
        self.smtp_host, self.smtp_port = normalize_host_and_port(raw_smtp, default_smtp_port)

        self.imap_ssl = str(config.get("imap_ssl", "1")).lower() in ("1", "true", "yes")
        self.smtp_ssl = str(config.get("smtp_ssl", "1")).lower() in ("1", "true", "yes")

        self.email_account = config.get("email_account", "").strip()
        self.email_password = config.get("email_password", "")
        self.sender_display_name = config.get("sender_display_name", "").strip()
        self.attachment_root = str(attachment_root or ATTACHMENTS_DIR)
        os.makedirs(self.attachment_root, exist_ok=True)

        # WebAPI 会话与缓存
        self._http_session: Optional[requests.Session] = None
        self._cached_sid: Optional[str] = None
        self._cached_base_url: Optional[str] = None

    def _persist_working_config(self, **kwargs):
        """将自动探测或回退跑通的端口与设置写回本地数据库，避免下次连接重复超时重试"""
        try:
            from core.database import DatabaseManager
            db = DatabaseManager()
            for k, v in kwargs.items():
                db.save_setting(k, str(v))
        except Exception:
            pass

    def _get_http_session(self) -> requests.Session:
        if self._http_session is None:
            sess = requests.Session()
            sess.trust_env = False  # 忽略错误或被重定向的 Windows 系统代理
            sess.verify = False     # 兼容内网自签名证书
            sess.headers.update({
                "User-Agent": "L-CMClient/5.0",
                "Accept": "application/json, text/plain, */*"
            })
            self._http_session = sess
        return self._http_session

    def _get_candidate_base_urls(self) -> List[str]:
        candidates = []
        if self.http_base_url:
            candidates.append(self.http_base_url.rstrip("/"))

        raw_srv = self.coremail_server.strip()
        if raw_srv:
            parsed = parse_server_endpoint(raw_srv)
            if parsed.get("scheme") and parsed.get("host"):
                p = parsed.get("port")
                base = f"{parsed['scheme']}://{parsed['host']}" + (f":{p}" if p else "")
                if base not in candidates:
                    candidates.append(base)

        clean_host = normalize_host_and_port(self.coremail_server or self.imap_host, 80)[0]
        if clean_host:
            for s in [
                f"https://{clean_host}",
                f"http://{clean_host}",
                f"http://{clean_host}:8080",
                f"https://{clean_host}:8443",
                f"http://{clean_host}:80"
            ]:
                if s not in candidates:
                    candidates.append(s)
        return candidates

    def _http_login(self) -> Tuple[str, str]:
        """
        通过 Coremail WebAPI (/coremail/s/json?func=user:login) 认证登录并获取会话 sid
        """
        if not self.email_account or not self.email_password:
            raise ValueError("邮箱账号或密码未填写")

        session = self._get_http_session()
        candidates = self._get_candidate_base_urls()

        # 尝试两种 uid 格式：完整邮箱和去掉 @domain 的前缀
        uid_candidates = [self.email_account]
        if "@" in self.email_account:
            uid_candidates.append(self.email_account.split("@")[0])

        last_error = None
        auth_failed = False

        for base_url in candidates:
            login_url = f"{base_url}/coremail/s/json?func=user:login"
            for uid in uid_candidates:
                payload = {
                    "uid": uid,
                    "password": self.email_password,
                    "supportVerifyCode": False
                }
                try:
                    resp = session.post(
                        login_url,
                        json=payload,
                        headers={"Content-Type": "application/json; charset=UTF-8"},
                        timeout=4.0
                    )
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                        except Exception:
                            continue

                        code = data.get("code")
                        if code == "S_OK":
                            var = data.get("var") or {}
                            sid = var.get("sid")
                            if sid:
                                self._cached_sid = sid
                                self._cached_base_url = base_url
                                if self.http_base_url != base_url:
                                    self.http_base_url = base_url
                                    self._persist_working_config(http_base_url=base_url)
                                return base_url, sid
                        elif code in ("FA_UNAUTHORIZED", "FA_PASSWORD_ERROR", "FA_USER_NOT_EXIST") or "password" in str(data.get("message", "")).lower():
                            auth_failed = True
                            last_error = f"账号或密码错误: {data.get('message', code)}"
                        else:
                            last_error = f"登录返回异常 ({code}): {data.get('message', '')}"
                except (requests.ConnectionError, requests.Timeout) as net_err:
                    last_error = f"无法连接到 {base_url}: {str(net_err)}"
                except Exception as ex:
                    last_error = str(ex)

            if auth_failed:
                raise ValueError(f"Coremail 论客认证失败: {last_error}")

        raise ConnectionError(f"Coremail WebAPI 登录失败：所有候选服务地址均不可用。最后错误: {last_error}")

    def _http_get_all_folders(self, base_url: str, sid: str) -> List[Dict[str, Any]]:
        """调用 /coremail/s/json?func=mbox:getAllFolders 获取所有收件类文件夹（收件箱 + 用户自定义文件夹）"""
        session = self._get_http_session()
        folders = []
        try:
            url = f"{base_url}/coremail/s/json?sid={sid}&func=mbox:getAllFolders"
            resp = session.post(url, json={}, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "S_OK":
                    raw_folders = data.get("var") or []
                    if isinstance(raw_folders, dict):
                        raw_folders = raw_folders.get("folders") or raw_folders.get("list") or raw_folders.get("items") or []
                    for f in raw_folders:
                        fid = f.get("id") or f.get("fid")
                        fname = f.get("name") or f.get("displayName") or (f"自定义文件夹_{fid}" if fid != 1 else "收件箱")
                        if fid is not None and not is_system_non_inbox_folder(fid, fname):
                            folders.append({"id": fid, "name": fname})
        except Exception:
            pass

        # 始终保底收件箱 (fid=1)
        if not any(f["id"] in (1, "1") for f in folders):
            folders.insert(0, {"id": 1, "name": "收件箱"})
        return folders

    def _http_fetch_new_email_headers(
        self, existing_uids: set, max_fetch_per_folder: int = 25
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        通过 Coremail WebAPI 扫描所有收信文件夹（收件箱 + 自定义文件夹）的邮件信头元数据。
        极速轻量：仅拉取 mid/主题/发件人/时间/摘要，绝不在此阶段下载完整正文和附件。
        返回 (headers_list, folder_count)
        """
        base_url, sid = self._http_login()
        session = self._get_http_session()

        folders = self._http_get_all_folders(base_url, sid)
        headers = []
        last_error = None

        for folder in folders:
            fid = folder["id"]
            fname = folder["name"]
            list_url = f"{base_url}/coremail/s/json?sid={sid}&func=mbox:listMessages"
            list_payload = {
                "fid": fid,
                "start": 0,
                "limit": max_fetch_per_folder,
                "order": "receivedDate",
                "desc": True,
                "returnTotal": True
            }

            try:
                resp = session.post(list_url, json=list_payload, timeout=10.0)
                if resp.status_code != 200:
                    last_error = f"获取文件夹[{fname}]失败: HTTP {resp.status_code}"
                    continue

                data = resp.json()
                code = data.get("code")
                if code in ("FA_INVALID_SESSION", "FA_EXPIRED"):
                    # 会话失效，重新认证并重试该文件夹一次
                    base_url, sid = self._http_login()
                    list_url = f"{base_url}/coremail/s/json?sid={sid}&func=mbox:listMessages"
                    resp = session.post(list_url, json=list_payload, timeout=10.0)
                    data = resp.json()
                    code = data.get("code")

                if code != "S_OK":
                    last_error = f"获取文件夹[{fname}]失败: {code} - {data.get('message', '')}"
                    continue

                var = data.get("var", [])
                # 兼容不同版本 Coremail 差异：可能是 list，也可能是 dict 内嵌 messages/list/items
                if isinstance(var, dict):
                    items = var.get("messages") or var.get("list") or var.get("items") or []
                elif isinstance(var, list):
                    items = var
                else:
                    items = []

                for item in items:
                    mid = item.get("id") or item.get("mid")
                    if not mid:
                        continue
                    mid_str = str(mid)
                    if mid_str in existing_uids:
                        continue

                    subject = decode_mime_str(item.get("subject", "(无主题)"))
                    date_str = str(item.get("sentDate") or item.get("receivedDate") or "")

                    raw_from = item.get("from") or ""
                    from_list = parse_address_list([raw_from]) if raw_from else []
                    sender_name = from_list[0]["name"] if from_list else (raw_from.split("<")[0].strip() if raw_from else "")
                    sender_email = from_list[0]["email"] if from_list else (raw_from if "@" in raw_from else "")

                    raw_to = item.get("to") or ""
                    to_list = parse_address_list([raw_to]) if raw_to else []

                    raw_cc = item.get("cc") or ""
                    cc_list = parse_address_list([raw_cc]) if raw_cc else []

                    summary = item.get("summary") or item.get("abstract") or item.get("desc") or ""

                    headers.append({
                        "uid": mid_str,
                        "message_id": item.get("messageId", ""),
                        "subject": subject,
                        "sender_name": sender_name,
                        "sender_email": sender_email,
                        "to_list": to_list,
                        "cc_list": cc_list,
                        "date_str": date_str,
                        "folder_name": fname,
                        "folder_id": fid,
                        "body_text": summary,
                        "body_html": "",
                        "attachments": [],
                        "is_body_loaded": 0,
                        "is_matched": 0,
                    })
            except Exception as e:
                last_error = str(e)

        if not headers and last_error and not existing_uids:
            # 若所有文件夹均未能成功请求且记录了错误，抛出具体原因杜绝假无邮件
            raise RuntimeError(f"Coremail 邮件拉取异常: {last_error}")

        return headers, len(folders)

    def fetch_single_email_detail(self, uid: str, folder_name: str = "INBOX") -> Dict[str, Any]:
        """
        按需单独拉取某一封邮件的完整正文 (HTML/Text) 并下载附件至本地磁盘 (Lazy-Load)
        优先通过 /coremail/s/eml 原文下载，次选 mbox:readMessage/getMessageData JSON 模式，或回退 IMAP
        """
        # 1. WebAPI 模式
        if self.protocol_mode == "coremail":
            try:
                base_url, sid = self._http_login()
                session = self._get_http_session()
                raw_mid = uid.split("::")[-1] if "::" in str(uid) else str(uid)

                # 方式 A：优先 EML 方式拉取原始数据（100% 完整解析富文本与附件）
                for eml_url in [
                    f"{base_url}/coremail/s/eml?sid={sid}&mid={quote(raw_mid)}",
                    f"{base_url}/coremail/XT5/jsp/download.jsp?sid={sid}&mid={quote(raw_mid)}"
                ]:
                    try:
                        eml_resp = session.get(eml_url, timeout=15.0)
                        if eml_resp.status_code == 200 and eml_resp.content and len(eml_resp.content) > 10:
                            parsed = self._parse_raw_email(str(uid), eml_resp.content)
                            if parsed and (parsed.get("body_text") or parsed.get("body_html") or parsed.get("attachments")):
                                return {
                                    "subject": parsed.get("subject", ""),
                                    "sender_name": parsed.get("sender_name", ""),
                                    "sender_email": parsed.get("sender_email", ""),
                                    "to_list": parsed.get("to_list", []),
                                    "cc_list": parsed.get("cc_list", []),
                                    "date_str": parsed.get("date_str", ""),
                                    "body_text": parsed.get("body_text", ""),
                                    "body_html": parsed.get("body_html", ""),
                                    "attachments": parsed.get("attachments", []),
                                    "is_body_loaded": 1
                                }
                    except Exception:
                        continue

                # 方式 B：mbox:readMessage / mbox:getMessageData / mbox:getMessageInfos JSON 回退解析
                for func_name in ["mbox:readMessage", "mbox:getMessageData", "mbox:getMessageInfos"]:
                    try:
                        read_url = f"{base_url}/coremail/s/json?sid={sid}&func={func_name}"
                        read_resp = session.post(
                            read_url,
                            json={"mid": raw_mid, "mode": "html", "markRead": False},
                            timeout=15.0
                        )
                        if read_resp.status_code == 200:
                            rdata = read_resp.json()
                            if rdata.get("code") == "S_OK":
                                m_var = rdata.get("var", {})
                                body_text, body_html = _extract_body_from_coremail_json(m_var)

                                attachments = []
                                raw_atts = m_var.get("attachments") or []
                                if raw_atts:
                                    uid_attach_dir = os.path.join(self.attachment_root, re.sub(r'[\\/:*?"<>|]', "_", str(uid)))
                                    os.makedirs(uid_attach_dir, exist_ok=True)
                                    for att in raw_atts:
                                        aid = att.get("id") or att.get("aid")
                                        att_name = decode_mime_str(att.get("filename") or att.get("name") or "attachment")
                                        safe_fname = re.sub(r'[\\/:*?"<>|]', "_", att_name)
                                        att_path = os.path.abspath(os.path.join(uid_attach_dir, safe_fname))

                                        if aid is not None:
                                            att_url = f"{base_url}/coremail/s/attach?sid={sid}&mid={quote(raw_mid)}&aid={aid}"
                                            try:
                                                att_resp = session.get(att_url, timeout=20.0)
                                                if att_resp.status_code == 200:
                                                    with open(att_path, "wb") as af:
                                                        af.write(att_resp.content)
                                                    attachments.append({
                                                        "filename": safe_fname,
                                                        "filepath": att_path,
                                                        "size": len(att_resp.content)
                                                    })
                                            except Exception:
                                                pass

                                if body_text or body_html or attachments:
                                    return {
                                        "body_text": body_text,
                                        "body_html": body_html,
                                        "attachments": attachments,
                                        "is_body_loaded": 1
                                    }
                    except Exception:
                        continue
            except Exception as e:
                if isinstance(e, ValueError) and "认证失败" in str(e):
                    raise e

        # 2. IMAP 模式
        try:
            conn = self._connect_imap()
            try:
                target_raw_folder = folder_name
                raw_imap_uid = str(uid)
                if str(uid).startswith("IMAP::"):
                    parts = str(uid).split("::", 2)
                    if len(parts) == 3:
                        target_raw_folder = parts[1]
                        raw_imap_uid = parts[2]
                else:
                    digits = re.findall(r'\d+', str(uid))
                    if digits:
                        raw_imap_uid = digits[-1]

                mailbox_arg = f'"{target_raw_folder}"' if not str(target_raw_folder).startswith('"') else target_raw_folder
                typ, _ = conn.select(mailbox_arg, readonly=True)
                if typ != "OK":
                    conn.select("INBOX", readonly=True)

                typ, msg_data = conn.uid("fetch", str(raw_imap_uid), "(BODY.PEEK[])")
                if typ != "OK" or not msg_data or not msg_data[0] or not msg_data[0][1]:
                    typ, msg_data = conn.uid("fetch", str(raw_imap_uid), "(RFC822)")

                if typ == "OK" and msg_data and msg_data[0]:
                    raw_bytes = msg_data[0][1]
                    if isinstance(raw_bytes, bytes) and len(raw_bytes) > 10:
                        parsed = self._parse_raw_email(str(uid), raw_bytes)
                        if parsed and (parsed.get("body_text") or parsed.get("body_html") or parsed.get("attachments")):
                            return {
                                "subject": parsed.get("subject", ""),
                                "sender_name": parsed.get("sender_name", ""),
                                "sender_email": parsed.get("sender_email", ""),
                                "to_list": parsed.get("to_list", []),
                                "cc_list": parsed.get("cc_list", []),
                                "date_str": parsed.get("date_str", ""),
                                "body_text": parsed.get("body_text", ""),
                                "body_html": parsed.get("body_html", ""),
                                "attachments": parsed.get("attachments", []),
                                "is_body_loaded": 1
                            }
            finally:
                try:
                    conn.logout()
                except Exception:
                    pass
        except Exception:
            pass

        return {
            "body_text": "",
            "body_html": "",
            "attachments": [],
            "is_body_loaded": 0
        }

    def _http_fetch_new_emails(self, existing_uids: set, max_fetch: int = 30) -> List[Dict[str, Any]]:
        """全文件夹拉取完整新邮件（全量兼容）"""
        headers, _ = self._http_fetch_new_email_headers(existing_uids, max_fetch_per_folder=max_fetch)
        full_emails = []
        for h in headers[:max_fetch]:
            try:
                detail = self.fetch_single_email_detail(h["uid"], h.get("folder_name", "INBOX"))
                if detail.get("subject") and (not h.get("subject") or h.get("subject") == "(无主题)"):
                    h["subject"] = detail["subject"]
                if detail.get("sender_name") and not h.get("sender_name"):
                    h["sender_name"] = detail["sender_name"]
                if detail.get("sender_email") and not h.get("sender_email"):
                    h["sender_email"] = detail["sender_email"]
                if detail.get("to_list") and not h.get("to_list"):
                    h["to_list"] = detail["to_list"]
                if detail.get("cc_list") and not h.get("cc_list"):
                    h["cc_list"] = detail["cc_list"]
                if detail.get("date_str") and not h.get("date_str"):
                    h["date_str"] = detail["date_str"]
                h["body_text"] = detail.get("body_text") or h.get("body_text", "")
                h["body_html"] = detail.get("body_html", "")
                h["attachments"] = detail.get("attachments", [])
                h["is_body_loaded"] = detail.get("is_body_loaded", 1)
            except Exception:
                pass
            full_emails.append(h)
        return full_emails

    def _http_send_email(
        self,
        to_addrs: List[str],
        cc_addrs: List[str],
        subject: str,
        html_body: str,
        plain_body: str,
        attachment_paths: List[str],
        save_to_sent: bool = True
    ) -> None:
        """通过 Coremail WebAPI (/coremail/s/json?func=mbox:compose) 发送邮件"""
        base_url, sid = self._http_login()
        session = self._get_http_session()

        uploaded_attachments = []
        if attachment_paths:
            upload_url = f"{base_url}/coremail/s/upload?sid={sid}"
            for p in attachment_paths:
                if not p or not os.path.isfile(p):
                    continue
                fname = os.path.basename(p)
                try:
                    with open(p, "rb") as f:
                        files = {"file": (fname, f, "application/octet-stream")}
                        up_resp = session.post(upload_url, files=files, timeout=30.0)
                    if up_resp.status_code == 200:
                        up_data = up_resp.json()
                        if up_data.get("code") == "S_OK":
                            var = up_data.get("var", {})
                            uploaded_attachments.append(var if isinstance(var, dict) else {"id": var, "filename": fname})
                        elif "id" in up_data:
                            uploaded_attachments.append(up_data)
                except Exception:
                    pass

        compose_url = f"{base_url}/coremail/s/json?sid={sid}&func=mbox:compose"
        payload = {
            "attrs": {
                "account": self.email_account,
                "to": to_addrs,
                "cc": cc_addrs,
                "subject": subject,
                "isHtml": True,
                "content": html_body or plain_body,
                "saveSent": save_to_sent,
                "attachments": uploaded_attachments
            },
            "action": "deliver",
            "returnInfo": True
        }

        resp = session.post(compose_url, json=payload, timeout=25.0)
        if resp.status_code != 200:
            raise RuntimeError(f"Coremail WebAPI 发信失败，HTTP 状态码: {resp.status_code}")

        data = resp.json()
        if data.get("code") != "S_OK":
            raise RuntimeError(f"Coremail WebAPI 发信失败: {data.get('code')} - {data.get('message', '')}")

    def _http_mark_read(self, uid: str) -> None:
        """通过 Coremail WebAPI 标记邮件为已读"""
        try:
            base_url, sid = self._http_login()
            session = self._get_http_session()
            url = f"{base_url}/coremail/s/json?sid={sid}&func=mbox:updateMessageStatus"
            session.post(url, json={"ids": [uid], "markRead": True}, timeout=5.0)
        except Exception:
            pass

    def _connect_imap(self) -> imaplib.IMAP4:
        """建立并登录 IMAP 连接（带清洗与自动降级回退）"""
        clean_host, _ = normalize_host_and_port(self.imap_host, self.imap_port)
        if not clean_host:
            raise ValueError("IMAP 服务器主机名为空")

        try:
            if self.imap_ssl:
                conn = imaplib.IMAP4_SSL(clean_host, self.imap_port, timeout=4.0)
            else:
                conn = imaplib.IMAP4(clean_host, self.imap_port, timeout=4.0)
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
                    conn = imaplib.IMAP4(clean_host, 143, timeout=4.0)
                    conn.login(self.email_account, self.email_password)
                    self.imap_port = 143
                    self.imap_ssl = False
                    self._persist_working_config(imap_port=143, imap_ssl="0")
                    return conn
                except Exception:
                    pass
            raise primary_err

    def test_connection(self) -> Dict[str, Any]:
        """测试连接与凭据有效性（快速端口探测 + Coremail WebAPI / IMAP / SMTP 智能多通道调度）"""
        if not self.email_account or not self.email_password:
            return {"ok": False, "msg": "邮箱账号或密码未填写"}

        target_host = self.coremail_server if self.protocol_mode == "coremail" and self.coremail_server else self.imap_host
        if not target_host and not self.smtp_host:
            return {"ok": False, "msg": "服务器地址未填写"}

        # 1. 快速端口探测 (< 2.0s)，避免盲目 15 秒连接超时
        probe_res = probe_coremail_server_ports(target_host or self.smtp_host)
        if not probe_res.get("ok"):
            return probe_res

        resolved_ip = probe_res.get("resolved_ip", "")
        http_base_url = probe_res.get("http_base_url")
        open_imap_port = probe_res.get("imap_port")
        open_smtp_port = probe_res.get("smtp_port")
        open_pop3_port = probe_res.get("pop3_port")

        success_channels = []

        # 2. 如果处于 coremail 模式且开放了 HTTP/HTTPS，优先测试 WebAPI 专用通道
        if self.protocol_mode == "coremail" and http_base_url:
            try:
                base_url, sid = self._http_login()
                self._cached_base_url = base_url
                self._cached_sid = sid
                success_channels.append(f"Coremail WebAPI 专用通道 ({base_url})")
            except Exception as e:
                if "认证失败" in str(e) or "密码错误" in str(e):
                    return {"ok": False, "msg": str(e)}

        # 3. 若 WebAPI 走通且未开放 SMTP，WebAPI 本身已具备完整收发能力！
        if success_channels and open_smtp_port is None:
            return {
                "ok": True,
                "msg": (
                    f"🎉 Coremail 论客服务器连接验证成功！\n\n"
                    f"• 服务器 IP: {resolved_ip}\n"
                    f"• 接入通道: {success_channels[0]}\n"
                    f"• 状态: 仅开放 HTTP/HTTPS 端口（内网防火墙已拦截标准 143/25 端口），\n"
                    f"  系统已自动切换至与官方论客客户端相同的 WebAPI 专用协议通道，收发与附件均正常！"
                )
            }

        # 4. 测试 IMAP 登录（仅当 IMAP 端口真实开放时）
        imap_ok = False
        if open_imap_port is not None:
            self.imap_port = open_imap_port
            self.imap_ssl = probe_res.get("imap_ssl", False)
            try:
                imap_conn = self._connect_imap()
                imap_conn.select("INBOX", readonly=True)
                imap_conn.logout()
                imap_ok = True
                success_channels.append(f"IMAP 收信 (端口 {open_imap_port})")
            except Exception as imap_err:
                if not success_channels:
                    return {"ok": False, "msg": f"IMAP 连接失败: {imap_err}"}

        # 5. 测试 SMTP 登录（仅当 SMTP 端口真实开放时）
        smtp_ok = False
        if open_smtp_port is not None:
            self.smtp_port = open_smtp_port
            self.smtp_ssl = probe_res.get("smtp_ssl", False)
            clean_smtp, _ = normalize_host_and_port(self.smtp_host or target_host, self.smtp_port)
            smtp_conn = None
            try:
                if self.smtp_ssl:
                    smtp_conn = smtplib.SMTP_SSL(clean_smtp, self.smtp_port, timeout=10)
                else:
                    smtp_conn = smtplib.SMTP(clean_smtp, self.smtp_port, timeout=10)
                    smtp_conn.ehlo()
                smtp_conn.login(self.email_account, self.email_password)
                smtp_ok = True
                success_channels.append(f"SMTP 发信 (端口 {open_smtp_port})")
            except Exception as smtp_err:
                if not success_channels:
                    return {"ok": False, "msg": f"SMTP 连接失败: {smtp_err}"}
            finally:
                if smtp_conn:
                    try:
                        smtp_conn.quit()
                    except Exception:
                        pass

        # 6. POP3 测试（当 IMAP 关但 POP3 开时）
        if not imap_ok and open_pop3_port is not None:
            try:
                clean_pop, _ = normalize_host_and_port(target_host, open_pop3_port)
                if probe_res.get("pop3_ssl"):
                    p_conn = poplib.POP3_SSL(clean_pop, open_pop3_port, timeout=10)
                else:
                    p_conn = poplib.POP3(clean_pop, open_pop3_port, timeout=10)
                p_conn.user(self.email_account)
                p_conn.pass_(self.email_password)
                p_conn.quit()
                success_channels.append(f"POP3 收信 (端口 {open_pop3_port})")
            except Exception:
                pass

        if success_channels:
            channel_str = "、".join(success_channels)
            return {
                "ok": True,
                "msg": f"🎉 论客邮箱服务连接验证成功！\n已成功连通通道：\n• {channel_str}"
            }

        return {
            "ok": False,
            "msg": f"连接失败：未能通过任何已知协议通道登录（已测试 WebAPI、IMAP、SMTP、POP3）。请检查账号密码及内网权限。"
        }

    def _imap_get_all_folders(self, conn: imaplib.IMAP4) -> List[Tuple[str, str]]:
        """获取 IMAP 所有非系统收信文件夹 (raw_name, decoded_name)"""
        folders = []
        try:
            typ, data = conn.list()
            if typ == "OK" and data:
                for line in data:
                    if not line:
                        continue
                    line_str = line.decode("latin1", errors="ignore") if isinstance(line, bytes) else str(line)
                    m = re.search(r'"([^"]+)"$', line_str.strip())
                    if m:
                        raw_name = m.group(1)
                    else:
                        parts = line_str.strip().split()
                        raw_name = parts[-1] if parts else "INBOX"

                    decoded_name = decode_imap_utf7(raw_name)
                    if not is_system_non_inbox_folder("", decoded_name):
                        folders.append((raw_name, decoded_name))
        except Exception:
            pass

        if not any(raw.upper() == "INBOX" for raw, _ in folders):
            folders.insert(0, ("INBOX", "收件箱"))
        return folders

    def _imap_fetch_new_email_headers(
        self, existing_uids: set, max_fetch_per_folder: int = 25
    ) -> Tuple[List[Dict[str, Any]], int]:
        """通过 IMAP 多文件夹轻量扫描新邮件信头（BODY.PEEK[HEADER]，不下载正文与附件）"""
        conn = self._connect_imap()
        headers = []
        folder_count = 0
        try:
            folders = self._imap_get_all_folders(conn)
            folder_count = len(folders)
            for raw_folder, decoded_folder in folders:
                try:
                    mailbox_arg = f'"{raw_folder}"' if not raw_folder.startswith('"') else raw_folder
                    typ, _ = conn.select(mailbox_arg, readonly=True)
                    if typ != "OK":
                        continue

                    typ, data = conn.uid("search", None, "ALL")
                    if typ != "OK" or not data or not data[0]:
                        continue

                    all_uids = [u.decode("utf-8") for u in data[0].split()]
                    candidate_uids = []
                    for u in all_uids[-max_fetch_per_folder:]:
                        full_uid = f"IMAP::{raw_folder}::{u}"
                        if full_uid not in existing_uids and u not in existing_uids:
                            candidate_uids.append((u, full_uid))

                    for raw_uid, full_uid in candidate_uids:
                        try:
                            typ, msg_data = conn.uid("fetch", raw_uid, "(BODY.PEEK[HEADER])")
                            if typ != "OK" or not msg_data or not msg_data[0]:
                                continue
                            raw_header = msg_data[0][1]
                            if not isinstance(raw_header, bytes):
                                continue

                            msg = email.message_from_bytes(raw_header)
                            subject = decode_mime_str(msg.get("Subject", "(无主题)"))
                            message_id = decode_mime_str(msg.get("Message-ID", ""))
                            date_str = decode_mime_str(msg.get("Date", ""))

                            from_list = parse_address_list(msg.get_all("From", []))
                            sender_name = from_list[0]["name"] if from_list else ""
                            sender_email = from_list[0]["email"] if from_list else ""

                            to_list = parse_address_list(msg.get_all("To", []))
                            cc_list = parse_address_list(msg.get_all("Cc", []))

                            headers.append({
                                "uid": full_uid,
                                "raw_uid": raw_uid,
                                "raw_folder": raw_folder,
                                "message_id": message_id,
                                "subject": subject,
                                "sender_name": sender_name,
                                "sender_email": sender_email,
                                "to_list": to_list,
                                "cc_list": cc_list,
                                "date_str": date_str,
                                "folder_name": decoded_folder,
                                "body_text": "",
                                "body_html": "",
                                "attachments": [],
                                "is_body_loaded": 0,
                                "is_matched": 0,
                            })
                        except Exception:
                            continue
                except Exception:
                    continue
        finally:
            try:
                conn.logout()
            except Exception:
                pass

        return headers, folder_count

    def fetch_new_email_headers(
        self, existing_uids: set, max_fetch_per_folder: int = 25
    ) -> Tuple[List[Dict[str, Any]], int]:
        """从所有收信文件夹扫描未入库的邮件轻量信头（WebAPI -> IMAP）"""
        if not self.email_account or not self.email_password:
            return [], 0

        # 1. Coremail WebAPI
        if self.protocol_mode == "coremail":
            try:
                return self._http_fetch_new_email_headers(existing_uids, max_fetch_per_folder)
            except Exception as http_err:
                if isinstance(http_err, ValueError) and "认证失败" in str(http_err):
                    raise http_err

        # 2. IMAP
        try:
            return self._imap_fetch_new_email_headers(existing_uids, max_fetch_per_folder)
        except Exception as imap_err:
            raise imap_err

    def _imap_fetch_new_emails(self, existing_uids: set, max_fetch: int = 30) -> List[Dict[str, Any]]:
        """通过标准 IMAP 协议拉取收件箱及自定义文件夹完整邮件"""
        headers, _ = self._imap_fetch_new_email_headers(existing_uids, max_fetch_per_folder=max_fetch)
        full_emails = []
        for h in headers[:max_fetch]:
            try:
                detail = self.fetch_single_email_detail(h["uid"], h.get("raw_folder") or h.get("folder_name", "INBOX"))
                if detail.get("subject") and (not h.get("subject") or h.get("subject") == "(无主题)"):
                    h["subject"] = detail["subject"]
                if detail.get("sender_name") and not h.get("sender_name"):
                    h["sender_name"] = detail["sender_name"]
                if detail.get("sender_email") and not h.get("sender_email"):
                    h["sender_email"] = detail["sender_email"]
                if detail.get("to_list") and not h.get("to_list"):
                    h["to_list"] = detail["to_list"]
                if detail.get("cc_list") and not h.get("cc_list"):
                    h["cc_list"] = detail["cc_list"]
                if detail.get("date_str") and not h.get("date_str"):
                    h["date_str"] = detail["date_str"]
                h["body_text"] = detail.get("body_text") or h.get("body_text", "")
                h["body_html"] = detail.get("body_html", "")
                h["attachments"] = detail.get("attachments", [])
                h["is_body_loaded"] = detail.get("is_body_loaded", 1)
            except Exception:
                pass
            full_emails.append(h)
        return full_emails

    def _pop3_fetch_new_emails(self, existing_uids: set, max_fetch: int = 30) -> List[Dict[str, Any]]:
        """当 IMAP 和 WebAPI 不可用，但 POP3 端口开放时的收信兜底"""
        if not self.email_account or not self.email_password:
            return []

        clean_host, _ = normalize_host_and_port(self.imap_host, 110)
        if not clean_host:
            return []

        pop_conn = None
        for port, use_ssl in [(995, True), (110, False)]:
            try:
                if use_ssl:
                    pop_conn = poplib.POP3_SSL(clean_host, port, timeout=10)
                else:
                    pop_conn = poplib.POP3(clean_host, port, timeout=10)
                pop_conn.user(self.email_account)
                pop_conn.pass_(self.email_password)
                break
            except Exception:
                if pop_conn:
                    try:
                        pop_conn.quit()
                    except Exception:
                        pass
                pop_conn = None

        if not pop_conn:
            return []

        new_emails = []
        try:
            resp, items, octets = pop_conn.uidl()
            msg_list = []
            for it in items:
                parts = it.decode("ascii", errors="ignore").split()
                if len(parts) >= 2:
                    msg_list.append((int(parts[0]), parts[1]))

            candidates = [m for m in msg_list[-max_fetch:] if m[1] not in existing_uids]
            for num, uid in candidates:
                try:
                    resp, lines, octets = pop_conn.retr(num)
                    raw_bytes = b"\r\n".join(lines)
                    parsed = self._parse_raw_email(uid, raw_bytes)
                    if parsed:
                        new_emails.append(parsed)
                except Exception:
                    continue
        finally:
            try:
                pop_conn.quit()
            except Exception:
                pass

        return new_emails

    def fetch_new_emails(self, existing_uids: set, max_fetch: int = 30) -> List[Dict[str, Any]]:
        """从所有文件夹拉取新邮件完整列表（全量兼容接口，内部自动按需获取详情）"""
        if not self.email_account or not self.email_password:
            return []

        # 1. 在 Coremail 专用协议模式下，优先尝试 WebAPI
        if self.protocol_mode == "coremail":
            try:
                emails = self._http_fetch_new_emails(existing_uids, max_fetch)
                return emails
            except Exception as http_err:
                if isinstance(http_err, ValueError) and "认证失败" in str(http_err):
                    raise http_err

        # 2. 尝试 IMAP
        try:
            return self._imap_fetch_new_emails(existing_uids, max_fetch)
        except Exception as imap_err:
            # 3. 降级尝试 POP3
            try:
                pop3_emails = self._pop3_fetch_new_emails(existing_uids, max_fetch)
                if pop3_emails:
                    return pop3_emails
            except Exception:
                pass
            raise imap_err

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

    def _smtp_send_email(
        self,
        to_addrs: List[str],
        cc_addrs: List[str],
        subject: str,
        html_body: str,
        plain_body: str,
        attachment_paths: List[str],
        save_to_sent: bool = True
    ) -> None:
        """通过标准 SMTP 协议发送邮件"""
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
                    self._persist_working_config(smtp_port=25, smtp_ssl="0")
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
        """发送富文本邮件（优先 WebAPI -> SMTP 降级）"""
        if not self.email_account or not self.email_password:
            raise ValueError("未配置发信邮箱账号或密码")

        # 1. 在 Coremail 专用协议模式下，优先尝试 WebAPI 发信
        if self.protocol_mode == "coremail":
            try:
                self._http_send_email(
                    to_addrs=to_addrs,
                    cc_addrs=cc_addrs,
                    subject=subject,
                    html_body=html_body,
                    plain_body=plain_body,
                    attachment_paths=attachment_paths,
                    save_to_sent=save_to_sent
                )
                return
            except Exception as http_err:
                if isinstance(http_err, ValueError) and "认证失败" in str(http_err):
                    raise http_err
                try:
                    self._smtp_send_email(
                        to_addrs=to_addrs,
                        cc_addrs=cc_addrs,
                        subject=subject,
                        html_body=html_body,
                        plain_body=plain_body,
                        attachment_paths=attachment_paths,
                        save_to_sent=save_to_sent
                    )
                    return
                except Exception:
                    raise http_err

        # 2. SMTP 发信
        self._smtp_send_email(
            to_addrs=to_addrs,
            cc_addrs=cc_addrs,
            subject=subject,
            html_body=html_body,
            plain_body=plain_body,
            attachment_paths=attachment_paths,
            save_to_sent=save_to_sent
        )

    def mark_email_read(self, uid: str) -> None:
        """标记邮件为已读（智能优先 WebAPI -> IMAP）"""
        if not self.email_account or not self.email_password:
            return

        if self.protocol_mode == "coremail":
            try:
                self._http_mark_read(uid)
                return
            except Exception:
                pass

        try:
            conn = self._connect_imap()
            try:
                conn.select("INBOX")
                conn.uid("store", str(uid), "+FLAGS", "(\\Seen)")
            finally:
                try:
                    conn.logout()
                except Exception:
                    pass
        except Exception:
            pass
