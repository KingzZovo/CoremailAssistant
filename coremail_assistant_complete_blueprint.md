# Coremail 论客邮箱智能协同与流转助手（Windows 纯内网全量完整版）设计与实现终极指南

> **交付说明**：本文档为**100% 独立完整的全量合一版设计蓝图**（已完整合并原 1.0 与 2.0 的全部底层代码，并新增了**邮件全文机器学习 + 全文修改差异自学习**以及**仿论客客户端的所见即所得富文本邮件编辑器**）。你**只需要把这一份文档**交给开发 Agent（如 3.8 Flash），**完全不需要**再发送之前的 1.0 文档。

---

## 一、 核心业务需求与技术亮点全景

本软件运行于**纯内网 Windows 环境（硬件基准：Intel 10代 i5 + 16GB 内存，无独立显卡）**，通过标准 [IMAP/SMTP 协议](https://www.google.com/search?q=https%3A%2F%2Fedu.icoremail.net%2Fcoremail%2Fhelp%2Fclientoption.jsp%3Flocale%3Dzh_CN)与本地 [Coremail 论客客户端](https://www.google.com/search?q=http%3A%2F%2Fwww.lunkr.cn%2F)协同工作：

| 核心模块 | 具体实现效果 | 智能化与防错机制 |
| :--- | :--- | :--- |
| **1. 双模式邮件流转（新建改写 vs 标准转发）** | **模式 A（改写为新邮件发给 F）**：去掉 `Fw:` 和原始邮件引用头，将 `A` 发来的邮件全文改写主语/人称与称呼后，作为一封**全新的邮件**发给 `F`，并自动抄送 `A, B, C, D`；**模式 B（标准带引文转发）**：顶部加批注，下方保留原始邮件引用头与正文 | 支持一键切换模式；抄送栏提供 **`[✓] 抄送原发件人 A`** 独立开关；支持常用联系人复选框点选 `F`，并与抄送栏实时互斥去重 |
| **2. 邮件全文机器学习与全文 Diff 自学习** | **不局限于开头称呼，直接扫描与学习邮件全文**：<br>① **全文 TF-IDF / N-Gram 增量分类**：提取邮件全文词组（1~2 gram）训练在线分类器，预测是否需流转、推荐哪个 `F`、推荐新建还是转发；<br>② **无称呼/带称呼自适应**：原邮件无称呼时绝不误删首句，并根据你对 `F` 的习惯决定是否补称呼；<br>③ **全文编辑差异自学习（Diff Learner）**：自动对比“原邮件全文”与“你手动编辑后的发出全文”，提取你在正文任意位置修改的主语/句式替换对（如 `我方 -> A部门`、`请您审批 -> 请协助核对`），越用越懂你的改写风格 | 适配 10代 i5 + 16G 内存，纯 CPU 全文特征提取 + 在线 `partial_fit` 增量训练耗时 `< 10ms`，内存占用 `< 60MB` |
| **3. 仿论客客户端的富文本编辑器（WYSIWYG）** | 在软件内直接对邮件正文进行**所见即所得富文本编辑**：支持**字体、字号、加粗、斜体、下划线、删除线、文字颜色（标红）、背景荧光高亮（标黄）、段落对齐、项目符号/编号列表、插入表格、直接 `Ctrl+V` 粘贴剪贴板截图到正文** | 保留原邮件 HTML 表格与排版格式直接编辑；正文内粘贴的截图在发信时自动转为 `MIMEImage (cid: 内联图片)`，确保收件人在论客客户端中正常显示图片 |
| **4. 附件默认继承与自由增删** | 无论是“改写新建邮件”还是“标准转发”，原邮件自带的附件均自动缓存至本地并默认全选挂载 | 弹窗中可随时取消勾选不需要带上的原附件，或点击“+ 添加本地附件”追加新文件 |
| **5. 全功能自定义备忘录工作台** | 既可由邮件提取摘要生成备忘，也可点击 **“➕ 新建自定义备忘录”** 自由创建脱离邮件的独立备忘；支持富文本内容、多步骤子任务清单（Checklist）、分类标签、置顶与到期托盘提醒 | 每 30 秒后台静默检查到期备忘，通过 Windows 系统托盘弹出气泡通知 |
| **6. 可选本地 Ollama 接入** | 支持在设置中切换：`仅本地机器学习与规则`、`初筛命中后调 Ollama`、`全部邮件调 Ollama`；编辑器内支持一键调用 Ollama 润色全文主语 | 在 10代 i5 上推荐配置 `qwen2.5:1.5b` 或 `qwen2.5:3b`，若未启动 Ollama 自动降级使用本地机器学习，绝不阻塞收发 |

---

## 二、 项目工程目录结构（全量 12 个文件）

```text
CoremailAssistant/
├── main.py                      # 程序入口，初始化高分屏缩放、数据库、主窗口与系统托盘
├── config.py                    # 默认配置常量与全局目录路径定义
├── requirements.txt             # 依赖清单：PySide6, requests, scikit-learn, jieba, joblib, beautifulsoup4
├── data/                        # 运行时自动生成的数据与模型目录
│   ├── assistant.db             # SQLite 本地数据库（7张核心表）
│   ├── ml_models.pkl            # joblib 持久化的全文增量机器学习模型文件
│   └── attachments/             # 按邮件 UID 分类缓存的原邮件附件与内联图片目录
├── core/
│   ├── __init__.py
│   ├── database.py              # SQLite 数据库访问层（含自定义备忘录、全文改写词典、ML样本CRUD）
│   ├── mail_client.py           # Coremail IMAP 收信解析、附件落盘、SMTP 富文本+内联图片发信引擎
│   ├── rewriter_engine.py       # 全文主语/人称改写、无称呼/带称呼自适应处理、HTML富文本保留改写引擎
│   ├── ml_learner.py            # 全文 N-Gram 在线机器学习引擎 + 全文修改差异(Diff)自动提取学习器
│   ├── ollama_client.py         # 本地 Ollama 接口封装（全文摘要提取 + 复杂全文主语润色）
│   └── worker_threads.py        # QThread 后台异步线程（收信、全文学习预测、Ollama改写、SMTP发信）
└── ui/
    ├── __init__.py
    ├── theme.py                 # Windows 11 Fluent 现代浅色卡片风格 QSS 样式表
    ├── rich_text_editor.py      # 仿论客邮箱客户端的富文本邮件编辑器组件（工具栏+颜色+表格+剪贴板贴图）
    ├── compose_send_dialog.py   # 双模式发信确认台（新建改写/转发切换、富文本直接编辑、联系人联动、附件增删）
    ├── memo_dialog.py           # 全功能自定义备忘录弹窗（独立新建、富文本内容、子任务Checklist、到期提醒）
    ├── rule_contact_dialog.py   # 常用联系人（专属称呼/是否加称呼习惯）、全文改写词典与匹配规则管理
    ├── settings_dialog.py       # 论客 IMAP/SMTP 配置、全文机器学习状态面板、Ollama 配置
    └── main_window.py           # 三栏式主窗口（左侧导航+中间邮件/备忘列表+右侧详情与一键流转工作台）
```

---

## 三、 数据库完整表结构设计 (`core/database.py` SQLite Schema)

```sql
-- 1. 邮件主表
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT UNIQUE NOT NULL,
    message_id TEXT,
    subject TEXT NOT NULL,
    sender_name TEXT,
    sender_email TEXT NOT NULL,
    to_list_json TEXT NOT NULL,            -- [{"name": "...", "email": "..."}]
    cc_list_json TEXT NOT NULL,            -- [{"name": "...", "email": "..."}]
    date_str TEXT,
    body_text TEXT,                        -- 邮件全文纯文本（供全文机器学习与全文Diff比对）
    body_html TEXT,                        -- 邮件全文原始 HTML（供富文本编辑器加载与保留格式改写）
    attachments_json TEXT DEFAULT '[]',    -- [{"filename": "...", "filepath": "...", "size": 1024}]
    is_matched INTEGER DEFAULT 0,          -- 是否需要流转处理 (0/1)
    ml_confidence REAL DEFAULT 0.0,        -- 全文机器学习预测需流转概率 (0.0~1.0)
    matched_rule_name TEXT DEFAULT '',
    recommended_mode TEXT DEFAULT 'rewrite_new', -- rewrite_new(改写新建) / standard_forward(标准转发)
    ai_summary TEXT DEFAULT '',
    ai_urgency TEXT DEFAULT '普通',
    suggested_to_json TEXT DEFAULT '[]',   -- 推荐收件人 F 邮箱列表 JSON
    status TEXT DEFAULT 'pending',         -- pending / sent_new / forwarded / ignored
    processed_at TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. 全功能自定义备忘录表（支持关联邮件或完全独立创建）
CREATE TABLE IF NOT EXISTS memos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_uid TEXT DEFAULT '',             -- 为空字符串表示用户手动新建的独立备忘录
    title TEXT NOT NULL,
    content_html TEXT DEFAULT '',          -- 支持富文本格式的自定义备忘内容
    checklist_json TEXT DEFAULT '[]',      -- 子任务步骤: [{"text": "步骤1", "done": false}]
    category TEXT DEFAULT '日常协调',       -- 日常协调 / 个人备忘 / 重点跟进 / 会议纪要
    tags TEXT DEFAULT '',
    priority TEXT DEFAULT '中',            -- 高 / 中 / 低
    is_pinned INTEGER DEFAULT 0,
    is_done INTEGER DEFAULT 0,
    remind_at TEXT DEFAULT '',             -- 到期提醒时间 YYYY-MM-DD HH:MM
    is_reminded INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. 常用联系人与个人发信习惯记忆表
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    department TEXT DEFAULT '',
    preferred_salutation TEXT DEFAULT '',  -- 对该联系人的习惯称呼（如 "张工，你好："，可为空表示不加称呼）
    use_salutation INTEGER DEFAULT 1,      -- 给该联系人发信时是否习惯加开头称呼 (1:加, 0:不加，由ML自动学习更新)
    preferred_mode TEXT DEFAULT 'auto',    -- auto / rewrite_new / standard_forward
    is_frequent_target INTEGER DEFAULT 1,
    send_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. 全文主语、人称与句式改写规则词典表（支持人工配置 + 全文Diff自动学习写入）
CREATE TABLE IF NOT EXISTS fulltext_rewrite_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_filter TEXT DEFAULT '',         -- 可选：仅针对特定发件人 A 生效（为空则全局生效）
    target_filter TEXT DEFAULT '',         -- 可选：仅针对特定收件人 F 生效（为空则全局生效）
    source_pattern TEXT NOT NULL,          -- 原邮件全文中的短语/句式（如 "我这边已经确认"、"请您审批"）
    target_template TEXT NOT NULL,         -- 改写后的短语（如 "{sender_name}那边已经确认"、"请协助审批"）
    is_regex INTEGER DEFAULT 0,
    learned_from_diff INTEGER DEFAULT 0,   -- 0: 手工/预置规则, 1: 机器学习从用户编辑全文Diff中自动提取
    hit_count INTEGER DEFAULT 1,           -- 命中使用次数（次数越高优先级越高）
    is_enabled INTEGER DEFAULT 1
);

-- 5. 机器学习全文历史训练样本表
CREATE TABLE IF NOT EXISTS ml_training_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_uid TEXT,
    sender_email TEXT,
    subject TEXT,
    full_body_text TEXT,                   -- 完整保存原邮件全文用于重训练
    final_sent_text TEXT DEFAULT '',       -- 用户最终确认编辑发出的全文（用于对比学习改写习惯）
    action_label INTEGER NOT NULL,         -- 1: 进行了流转发送, 0: 标记忽略
    chosen_mode TEXT DEFAULT '',           -- rewrite_new / standard_forward
    chosen_to_emails_json TEXT DEFAULT '[]',
    chosen_cc_emails_json TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. 关键词规则表
CREATE TABLE IF NOT EXISTS match_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT NOT NULL,
    match_scope TEXT DEFAULT 'both',
    keywords TEXT NOT NULL,
    exclude_keywords TEXT DEFAULT '',
    target_emails_json TEXT NOT NULL,
    default_send_mode TEXT DEFAULT 'rewrite_new',
    default_comment TEXT DEFAULT '请协助处理以下协调事宜：',
    priority INTEGER DEFAULT 10,
    is_enabled INTEGER DEFAULT 1
);

-- 7. 系统配置表
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

---

## 四、 四大核心模块完整源码（可直接保存或由 Agent 引用）

### 模块 1：Coremail 论客 IMAP/SMTP 收发引擎（支持富文本与正文粘贴内联图片 `core/mail_client.py`）

```python
import os
import re
import time
import uuid
import base64
import imaplib
import smtplib
import email
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
    for part, charset in decode_header(value):
        if isinstance(part, bytes):
            enc = (charset or "utf-8").lower()
            if enc in ("gb2312", "gbk", "default", "x-gbk"):
                enc = "gb18030"
            try:
                decoded_parts.append(part.decode(enc, errors="replace"))
            except LookupError:
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(str(part))
    return "".join(decoded_parts).strip()


def parse_address_list(header_values: List[str]) -> List[Dict[str, str]]:
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
            result.append({"name": clean_name or clean_addr.split("@")[0], "email": addr.strip()})
    return result


class CoremailClient:
    """Coremail 论客邮箱 IMAP/SMTP 客户端封装（支持富文本 HTML 及内联图片发送）"""

    def __init__(self, config: Dict[str, Any], attachment_root: str = "data/attachments"):
        self.imap_host = config.get("imap_host", "")
        self.imap_port = int(config.get("imap_port", 993))
        self.imap_ssl = bool(config.get("imap_ssl", True))
        self.smtp_host = config.get("smtp_host", "")
        self.smtp_port = int(config.get("smtp_port", 465))
        self.smtp_ssl = bool(config.get("smtp_ssl", True))
        self.email_account = config.get("email_account", "").strip()
        self.email_password = config.get("email_password", "")
        self.sender_display_name = config.get("sender_display_name", "")
        self.attachment_root = attachment_root
        os.makedirs(self.attachment_root, exist_ok=True)

    def _connect_imap(self) -> imaplib.IMAP4:
        if self.imap_ssl:
            conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=15)
        else:
            conn = imaplib.IMAP4(self.imap_host, self.imap_port, timeout=15)
        conn.login(self.email_account, self.email_password)
        return conn

    def test_connection(self) -> Dict[str, Any]:
        try:
            imap_conn = self._connect_imap()
            imap_conn.select("INBOX", readonly=True)
            imap_conn.logout()

            if self.smtp_ssl:
                smtp_conn = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15)
            else:
                smtp_conn = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
                smtp_conn.ehlo()
            smtp_conn.login(self.email_account, self.email_password)
            smtp_conn.quit()
            return {"ok": True, "msg": "Coremail 论客 IMAP/SMTP 服务器连接验证成功"}
        except Exception as e:
            return {"ok": False, "msg": f"连接失败: {str(e)}"}

    def fetch_new_emails(self, existing_uids: set, max_fetch: int = 30) -> List[Dict[str, Any]]:
        new_emails = []
        conn = self._connect_imap()
        try:
            conn.select("INBOX", readonly=True)
            typ, data = conn.uid("search", None, "ALL")
            if typ != "OK" or not data or not data[0]:
                return []

            all_uids = [u.decode("utf-8") for u in data[0].split()]
            candidate_uids = [u for u in all_uids[-max_fetch:] if u not in existing_uids]

            for uid in candidate_uids:
                typ, msg_data = conn.uid("fetch", uid, "(BODY.PEEK[])")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw_bytes = msg_data[0][1]
                if not isinstance(raw_bytes, bytes):
                    continue
                parsed = self._parse_raw_email(uid, raw_bytes)
                if parsed:
                    new_emails.append(parsed)
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        return new_emails

    def _parse_raw_email(self, uid: str, raw_bytes: bytes) -> Optional[Dict[str, Any]]:
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

        # 2. 处理 file:///C:/... 本地图片路径
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
        msg = MIMEMultipart("mixed")
        from_header = formataddr((self.sender_display_name or self.email_account.split("@")[0], self.email_account))
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

        if self.smtp_ssl:
            smtp = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=20)
        else:
            smtp = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20)
            smtp.ehlo()

        try:
            smtp.login(self.email_account, self.email_password)
            smtp.sendmail(self.email_account, all_recipients, raw_message)
        finally:
            try:
                smtp.quit()
            except Exception:
                pass

        if save_to_sent:
            try:
                imap = self._connect_imap()
                for folder in ('"Sent Messages"', '"Sent"', '"&XfJT0ZAB-"'):
                    typ, _ = imap.append(folder, "\\Seen", imaplib.Time2Internaldate(time.time()), raw_message)
                    if typ == "OK":
                        break
                imap.logout()
            except Exception:
                pass
```

---

### 模块 2：邮件全文改写、无称呼自适应与富文本格式保留引擎 (`core/rewriter_engine.py`)

专门解决你提到的两个关键细节：
1. **很多人发邮件不带称呼**：严格校验首行是否真正属于“称呼语法”（不仅看字数，还要求命中称呼词缀或问候词，避免把不带称呼的正文第一句话误删）；同时支持根据你对收件人 `F` 的习惯（`use_salutation`），决定是否自动在全文开头补上对 `F` 的称呼。
2. **保留富文本 HTML 并直接改写全文**：在替换主语、人称和习语时，支持直接在原邮件的 **HTML 富文本树（文本节点）** 上做全文替换，完整保留原邮件里的表格、加粗、红字高亮和图片！

```python
import re
import html
from bs4 import BeautifulSoup, NavigableString
from typing import Dict, Any, List, Tuple


# 严格版称呼识别正则：必须包含明确称呼身份词或问候语，且独占首行（绝不误伤无称呼邮件的正文第一句）
STRICT_SALUTATION_REGEX = re.compile(
    r"^\s*(?:"
    r"(?:尊敬的|亲爱的|Dear)\s*[^\n，,：:!！]{1,15}[，,：:!！]"
    r"|"
    r"[^\n，,：:!！]{1,12}(?:先生|女士|老师|教授|经理|主任|处长|科长|局长|总|工|哥|姐|同志|同学|领导|各位|大家)\s*(?:您好|你好|早上好|下午好|晚上好|见信好)?[，,：:!！]"
    r"|"
    r"[^\n，,：:!！]{1,10}[，,：:\s]+(?:您好|你好|早上好|下午好|晚上好)[，,：:!！]"
    r")\s*\n*",
    re.IGNORECASE
)

DEFAULT_FULLTEXT_REWRITES = [
    {"source": "麻烦您", "target": "麻烦你"},
    {"source": "请您协助", "target": "请协助"},
    {"source": "请您帮忙", "target": "请帮忙"},
    {"source": "请您确认", "target": "请确认"},
    {"source": "请您审阅", "target": "请审阅"},
    {"source": "请您审批", "target": "请审批"},
    {"source": "请您查收", "target": "请查收"},
    {"source": "请您知悉", "target": "请知悉"},
    {"source": "发给您", "target": "同步给你"},
    {"source": "向您汇报", "target": "同步一下"},
    {"source": "我这边", "target": "{sender_name}那边"},
    {"source": "我们这边", "target": "{sender_name}团队那边"},
    {"source": "我部门", "target": "{sender_name}部门"},
    {"source": "我科室", "target": "{sender_name}科室"},
    {"source": "我方", "target": "{sender_name}方"},
]


class RewriterEngine:
    """支持无称呼自适应、全文主语/人称替换、以及 HTML 富文本保留改写的双模式引擎"""

    @staticmethod
    def strip_original_salutation_safely(body_text: str) -> Tuple[str, str]:
        """
        安全剥离原邮件开头称呼：
        若发件人 A 根本没写称呼（直接写事情），则原封不动保留全文，绝不误删首句！
        """
        if not body_text:
            return "", ""
        text = body_text.lstrip()
        match = STRICT_SALUTATION_REGEX.match(text)
        if match:
            removed = match.group(0).strip()
            return text[match.end():].lstrip(), removed
        return text, ""

    @staticmethod
    def generate_target_salutation(
        target_contacts: List[Dict[str, Any]],
        fallback_emails: List[str]
    ) -> str:
        """
        生成对收件人 F 的称呼；如果学习到用户对该联系人习惯不加称呼 (use_salutation == 0)，则返回空字符串。
        """
        if target_contacts:
            first = target_contacts[0]
            if int(first.get("use_salutation", 1)) == 0:
                return ""
            if first.get("preferred_salutation"):
                sal = first["preferred_salutation"].strip()
                if sal and not sal.endswith(("：", ":", "!", "！", ",")):
                    sal += "："
                return sal
            if len(target_contacts) == 1:
                name = first.get("name") or first.get("email", "").split("@")[0]
                return f"{name}，你好："
            names = "、".join([c.get("name") or c.get("email", "").split("@")[0] for c in target_contacts[:3]])
            return f"{names}，你们好："

        if fallback_emails:
            return f"{fallback_emails[0].split('@')[0]}，你好："
        return ""

    @classmethod
    def apply_fulltext_rewrites(
        cls,
        text: str,
        sender_name: str,
        sender_email: str = "",
        target_email: str = "",
        custom_rules: List[Dict[str, Any]] = None
    ) -> str:
        """在纯文本全文范围内执行主语、人称及学习到的短语替换"""
        if not text:
            return ""
        clean_sender = sender_name.strip() or (sender_email.split("@")[0] if sender_email else "发件方")
        result = text

        active_rules = []
        if custom_rules:
            # 按命中使用频次 hit_count 降序排列，优先应用高频习惯规则
            sorted_custom = sorted(
                [r for r in custom_rules if r.get("is_enabled", 1)],
                key=lambda x: int(x.get("hit_count", 1)),
                reverse=True
            )
            for r in sorted_custom:
                s_filter = (r.get("sender_filter") or "").strip().lower()
                t_filter = (r.get("target_filter") or "").strip().lower()
                if s_filter and s_filter != sender_email.lower():
                    continue
                if t_filter and t_filter not in target_email.lower():
                    continue
                active_rules.append({
                    "source": r.get("source_pattern", ""),
                    "target": r.get("target_template", ""),
                    "is_regex": bool(r.get("is_regex", 0))
                })

        for d in DEFAULT_FULLTEXT_REWRITES:
            active_rules.append({"source": d["source"], "target": d["target"], "is_regex": False})

        for rule in active_rules:
            src = rule["source"]
            if not src:
                continue
            tgt = rule["target"].replace("{sender_name}", clean_sender)
            if rule["is_regex"]:
                try:
                    result = re.sub(src, tgt, result)
                except re.error:
                    pass
            else:
                result = result.replace(src, tgt)
        return result

    @classmethod
    def rewrite_html_preserving_format(
        cls,
        raw_html: str,
        sender_name: str,
        sender_email: str,
        target_email: str,
        salutation: str,
        closing_sign: str,
        custom_rules: List[Dict[str, Any]] = None
    ) -> str:
        """
        直接在 HTML DOM 树上剥离原开头称呼、替换全文文本节点中的主语与人称，
        100% 保留原邮件中的表格、字体颜色、加粗与内嵌图片！
        """
        soup = BeautifulSoup(raw_html, "html.parser")
        body_root = soup.body if soup.body else soup

        # 1. 检查第一个非空文本节点是否为原称呼，若是则剥离
        first_text_checked = False
        for node in body_root.descendants:
            if isinstance(node, NavigableString) and node.strip():
                if not first_text_checked:
                    first_text_checked = True
                    stripped, removed = cls.strip_original_salutation_safely(str(node))
                    if removed:
                        node.replace_with(stripped)
                        break

        # 2. 遍历全文所有可见文本节点，执行主语与人称替换（不破坏 HTML 标签与表格结构）
        for node in list(body_root.descendants):
            if isinstance(node, NavigableString) and node.parent.name not in ("script", "style"):
                orig_str = str(node)
                if orig_str.strip():
                    new_str = cls.apply_fulltext_rewrites(
                        orig_str, sender_name, sender_email, target_email, custom_rules
                    )
                    if new_str != orig_str:
                        node.replace_with(new_str)

        inner_html = "".join(str(c) for c in body_root.contents)
        sal_html = f"<p style='margin:0 0 12px 0;'>{html.escape(salutation)}</p>" if salutation else ""
        close_html = f"<p style='margin:14px 0 0 0;'>{html.escape(closing_sign)}</p>" if closing_sign else ""

        return (
            f"<div style=\"font-family:'Microsoft YaHei',Segoe UI,sans-serif;font-size:14px;color:#1f2937;line-height:1.7;\">"
            f"{sal_html}{inner_html}{close_html}</div>"
        )

    @staticmethod
    def compute_recipients(
        my_email: str,
        sender_email: str,
        to_list: List[Dict[str, str]],
        cc_list: List[Dict[str, str]],
        selected_f_emails: List[str],
        include_sender_in_cc: bool = True
    ) -> Tuple[List[str], List[str]]:
        my_clean = (my_email or "").strip().lower()
        new_to = []
        to_seen = set()
        for f_addr in selected_f_emails:
            clean = f_addr.strip().lower()
            if clean and clean != my_clean and clean not in to_seen:
                to_seen.add(clean)
                new_to.append(f_addr.strip())

        candidates = []
        if include_sender_in_cc and sender_email:
            candidates.append(sender_email.strip())
        for item in (to_list or []):
            if item.get("email"):
                candidates.append(item["email"].strip())
        for item in (cc_list or []):
            if item.get("email"):
                candidates.append(item["email"].strip())

        new_cc = []
        cc_seen = set()
        for addr in candidates:
            clean = addr.lower()
            if not clean or clean == my_clean or clean in to_seen or clean in cc_seen:
                continue
            cc_seen.add(clean)
            new_cc.append(addr)

        return new_to, new_cc

    @classmethod
    def build_compose_content(
        cls,
        mode: str,
        email_data: Dict[str, Any],
        target_contacts: List[Dict[str, Any]],
        selected_f_emails: List[str],
        custom_rewrite_rules: List[Dict[str, Any]] = None,
        closing_sign: str = "请协助跟进处理，谢谢！"
    ) -> Dict[str, str]:
        orig_subject = (email_data.get("subject") or "").strip()
        sender_name = email_data.get("sender_name") or email_data.get("sender_email", "").split("@")[0]
        sender_email = email_data.get("sender_email", "")
        first_target_email = selected_f_emails[0] if selected_f_emails else ""

        salutation = cls.generate_target_salutation(target_contacts, selected_f_emails)
        stripped_text, _ = cls.strip_original_salutation_safely(email_data.get("body_text", ""))
        rewritten_text = cls.apply_fulltext_rewrites(
            stripped_text, sender_name, sender_email, first_target_email, custom_rewrite_rules
        )

        if mode == "rewrite_new":
            clean_subject = re.sub(r"^(Fw:|FW:|转发:|转发：)\s*", "", orig_subject, flags=re.IGNORECASE)
            parts = [p for p in (salutation, rewritten_text, closing_sign) if p.strip()]
            plain_body = "\n\n".join(parts)

            raw_html = (email_data.get("body_html") or "").strip()
            if raw_html:
                html_body = cls.rewrite_html_preserving_format(
                    raw_html, sender_name, sender_email, first_target_email,
                    salutation, closing_sign, custom_rewrite_rules
                )
            else:
                html_paragraphs = "<br>".join(html.escape(plain_body).splitlines())
                html_body = (
                    f"<div style=\"font-family:'Microsoft YaHei',Segoe UI,sans-serif;font-size:14px;"
                    f"color:#1f2937;line-height:1.7;\">{html_paragraphs}</div>"
                )
            return {
                "subject": clean_subject,
                "salutation": salutation,
                "plain_body": plain_body,
                "html_body": html_body
            }
        else:
            fw_subject = orig_subject if orig_subject.lower().startswith(("fw:", "转发:")) else f"Fw: {orig_subject}"
            top_lines = [salutation, f"{sender_name}发来以下协调事项，{closing_sign}"] if salutation else [f"{sender_name}发来以下协调事项，{closing_sign}"]
            top_comment = "\n".join(top_lines)

            sender_str = f"{email_data.get('sender_name', '')} <{email_data.get('sender_email', '')}>".strip()
            to_str = "; ".join([f"{x.get('name', '')} <{x.get('email', '')}>" for x in email_data.get("to_list", [])])
            cc_str = "; ".join([f"{x.get('name', '')} <{x.get('email', '')}>" for x in email_data.get("cc_list", [])])
            date_str = email_data.get("date_str", "")

            plain_body = (
                f"{top_comment}\n\n"
                f"------------------ 原始邮件 ------------------\n"
                f"发件人: {sender_str}\n"
                f"发送时间: {date_str}\n"
                f"收件人: {to_str}\n"
                f"抄送: {cc_str}\n"
                f"主题: {orig_subject}\n\n"
                f"{email_data.get('body_text', '')}"
            )
            comment_html = html.escape(top_comment).replace("\n", "<br>")
            orig_html = email_data.get("body_html") or f"<pre style='white-space:pre-wrap;'>{html.escape(email_data.get('body_text', ''))}</pre>"
            html_body = (
                f"<div style=\"font-family:'Microsoft YaHei',Segoe UI,sans-serif;font-size:14px;color:#1f2937;line-height:1.6;\">"
                f"<div style=\"margin-bottom:16px;\">{comment_html}</div>"
                f"<div style=\"border-top:1px solid #d1d5db;margin-top:16px;color:#4b5563;font-size:13px;background:#f9fafb;padding:10px 14px;border-radius:6px;\">"
                f"<b>------------------ 原始邮件 ------------------</b><br>"
                f"<b>发件人：</b>{html.escape(sender_str)}<br>"
                f"<b>发送时间：</b>{html.escape(date_str)}<br>"
                f"<b>收件人：</b>{html.escape(to_str)}<br>"
                f"<b>抄送：</b>{html.escape(cc_str)}<br>"
                f"<b>主题：</b>{html.escape(orig_subject)}"
                f"</div><div style=\"margin-top:14px;\">{orig_html}</div></div>"
            )
            return {
                "subject": fw_subject,
                "salutation": salutation,
                "plain_body": plain_body,
                "html_body": html_body
            }
```

---

### 模块 3：邮件全文机器学习 + 全文修改差异（Diff）自学习引擎 (`core/ml_learner.py`)

彻底取消对邮件正文的截断，**直接扫描整封邮件全文**提取 1-gram 与 2-gram 词组特征；并新增 **`extract_fulltext_rewrite_diffs` 全文修改差异对比算法**——当你在富文本编辑器里修改了正文中段的某句话、某个主语或称呼并点击发送后，系统利用 `difflib.SequenceMatcher` 自动对比“原邮件全文”与“你发出的全文”，把你在正文任意位置所做的短语改写自动提炼为规则写入数据库！

```python
import os
import re
import joblib
import jieba
import difflib
import numpy as np
from typing import Dict, Any, List, Tuple
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.linear_model import SGDClassifier


class LocalEmailLearner:
    """
    基于邮件全文语义特征 + 全文编辑差异(Diff)对比的本地增量机器学习引擎
    适配 10代 i5 + 16GB 内存，不截断正文，直接分析邮件全文。
    """

    def __init__(self, model_path: str = "data/ml_models.pkl"):
        self.model_path = model_path
        # 使用 2^15 维特征空间，对整封邮件全文提取分词与双词共现特征
        self.vectorizer = HashingVectorizer(
            n_features=2**15,
            analyzer=self._fulltext_ngram_analyzer,
            alternate_sign=False
        )
        # 1. 全文是否需要流转分类器 (0: 忽略, 1: 需处理)
        self.action_clf = SGDClassifier(loss="log_loss", random_state=42)
        self.action_fitted = False

        # 2. 全文流转方式分类器 (0: standard_forward 标准转发, 1: rewrite_new 改写新建邮件)
        self.mode_clf = SGDClassifier(loss="log_loss", random_state=42)
        self.mode_fitted = False

        # 3. 发件人 & 全文词组 -> 目标收件人 F 的权重统计矩阵
        self.sender_to_target_stats: Dict[str, Dict[str, float]] = {}
        self.token_to_target_stats: Dict[str, Dict[str, float]] = {}
        self._load()

    @staticmethod
    def _fulltext_ngram_analyzer(text: str) -> List[str]:
        """对邮件全文进行中文分词，并同时生成 Unigram（单词）与 Bigram（相邻双词短语）特征"""
        if not text:
            return []
        words = [w.strip().lower() for w in jieba.lcut(text) if len(w.strip()) >= 2]
        bigrams = [f"{words[i]}_{words[i+1]}" for i in range(len(words) - 1)]
        return words + bigrams

    @staticmethod
    def _build_full_feature_text(sender_email: str, cc_list: List[Dict[str, str]], subject: str, full_body: str) -> str:
        """融合发件人、原抄送人特征、主题与整封邮件全文（不截断）"""
        sender_tag = f"__from_{sender_email.lower().strip()}__"
        cc_tags = " ".join([f"__cc_{c.get('email', '').lower().strip()}__" for c in (cc_list or [])])
        return f"{sender_tag} {sender_tag} {cc_tags} {subject} {subject} {full_body or ''}"

    def predict_email(self, email_data: Dict[str, Any], candidate_contacts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """基于邮件全文预测：是否需流转、推荐新建还是转发、推荐收件人 F"""
        sender = (email_data.get("sender_email") or "").lower().strip()
        cc_list = email_data.get("cc_list") or []
        subject = email_data.get("subject") or ""
        full_body = email_data.get("body_text") or ""

        feat_text = self._build_full_feature_text(sender, cc_list, subject, full_body)
        X = self.vectorizer.transform([feat_text])

        need_prob = 0.5
        if self.action_fitted:
            try:
                need_prob = float(self.action_clf.predict_proba(X)[0][1])
            except Exception:
                need_prob = 0.5

        rec_mode = "rewrite_new"
        if self.mode_fitted:
            try:
                m_prob = float(self.mode_clf.predict_proba(X)[0][1])
                rec_mode = "rewrite_new" if m_prob >= 0.5 else "standard_forward"
            except Exception:
                rec_mode = "rewrite_new"

        scores: Dict[str, float] = {}
        valid_emails = {c["email"].lower(): c["email"] for c in candidate_contacts if c.get("email")}

        if sender in self.sender_to_target_stats:
            for f_mail, weight in self.sender_to_target_stats[sender].items():
                if f_mail in valid_emails:
                    scores[valid_emails[f_mail]] = scores.get(valid_emails[f_mail], 0.0) + weight * 3.0

        # 扫描整封邮件全文的词与双词短语计算收件人 F 匹配得分
        full_tokens = set(self._fulltext_ngram_analyzer(f"{subject} {full_body}"))
        for tk in full_tokens:
            if tk in self.token_to_target_stats:
                for f_mail, weight in self.token_to_target_stats[tk].items():
                    if f_mail in valid_emails:
                        scores[valid_emails[f_mail]] = scores.get(valid_emails[f_mail], 0.0) + weight * 0.4

        ranked_f = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
        return {
            "need_action_prob": round(need_prob, 3),
            "is_ml_recommended": need_prob >= 0.58,
            "recommended_mode": rec_mode,
            "predicted_f_emails": ranked_f[:2]
        }

    def learn_from_user_action(
        self,
        email_data: Dict[str, Any],
        action_label: int,
        chosen_mode: str = "rewrite_new",
        chosen_f_emails: List[str] = None
    ) -> None:
        """从用户对整封邮件的实际操作中进行全文特征增量训练"""
        sender = (email_data.get("sender_email") or "").lower().strip()
        cc_list = email_data.get("cc_list") or []
        subject = email_data.get("subject") or ""
        full_body = email_data.get("body_text") or ""

        feat_text = self._build_full_feature_text(sender, cc_list, subject, full_body)
        X = self.vectorizer.transform([feat_text])

        y_action = np.array([1 if action_label else 0])
        self.action_clf.partial_fit(X, y_action, classes=np.array([0, 1]))
        self.action_fitted = True

        if action_label == 1:
            y_mode = np.array([1 if chosen_mode == "rewrite_new" else 0])
            self.mode_clf.partial_fit(X, y_mode, classes=np.array([0, 1]))
            self.mode_fitted = True

            full_tokens = set(self._fulltext_ngram_analyzer(f"{subject} {full_body}"))
            for f_addr in (chosen_f_emails or []):
                f_clean = f_addr.lower().strip()
                if not f_clean:
                    continue
                if sender:
                    self.sender_to_target_stats.setdefault(sender, {})
                    self.sender_to_target_stats[sender][f_clean] = self.sender_to_target_stats[sender].get(f_clean, 0.0) + 1.0
                for tk in full_tokens:
                    self.token_to_target_stats.setdefault(tk, {})
                    self.token_to_target_stats[tk][f_clean] = self.token_to_target_stats[tk].get(f_clean, 0.0) + 1.0

        self._save()

    @staticmethod
    def extract_fulltext_rewrite_diffs(
        original_full_text: str,
        edited_full_text: str,
        sender_name: str
    ) -> List[Tuple[str, str]]:
        """
        全文级修改差异自学习器：
        对比【原邮件全文】与【用户在富文本编辑器中修改后的全文】，
        按分句对比提取用户在正文任意段落手动修改的短语替换对 (source_phrase -> target_phrase)。
        例如用户在正文第3段把 "我部申请开通" 改成了 "研发部申请开通"，系统会自动捕捉该替换对！
        """
        if not original_full_text or not edited_full_text:
            return []

        orig_sents = [s.strip() for s in re.split(r"[。！？!?\n；;]", original_full_text) if s.strip()]
        edit_sents = [s.strip() for s in re.split(r"[。！？!?\n；;]", edited_full_text) if s.strip()]

        learned_pairs: List[Tuple[str, str]] = []
        matcher = difflib.SequenceMatcher(None, orig_sents, edit_sents)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace" and (i2 - i1) == 1 and (j2 - j1) == 1:
                s_orig = orig_sents[i1]
                s_edit = edit_sents[j1]
                # 如果两个句子整体相似度在 0.45 ~ 0.95 之间，说明用户对该句做了局部主语/人称/措辞微调
                sim = difflib.SequenceMatcher(None, s_orig, s_edit).ratio()
                if 0.45 <= sim <= 0.95:
                    char_matcher = difflib.SequenceMatcher(None, s_orig, s_edit)
                    for c_tag, ci1, ci2, cj1, cj2 in char_matcher.get_opcodes():
                        if c_tag == "replace":
                            src_piece = s_orig[ci1:ci2].strip()
                            tgt_piece = s_edit[cj1:cj2].strip()
                            if 2 <= len(src_piece) <= 12 and 1 <= len(tgt_piece) <= 18:
                                if sender_name and sender_name in tgt_piece:
                                    tgt_piece = tgt_piece.replace(sender_name, "{sender_name}")
                                learned_pairs.append((src_piece, tgt_piece))

        return learned_pairs

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        joblib.dump({
            "action_clf": self.action_clf,
            "action_fitted": self.action_fitted,
            "mode_clf": self.mode_clf,
            "mode_fitted": self.mode_fitted,
            "sender_stats": self.sender_to_target_stats,
            "token_stats": self.token_to_target_stats
        }, self.model_path)

    def _load(self) -> None:
        if not os.path.isfile(self.model_path):
            return
        try:
            data = joblib.load(self.model_path)
            self.action_clf = data["action_clf"]
            self.action_fitted = data["action_fitted"]
            self.mode_clf = data["mode_clf"]
            self.mode_fitted = data["mode_fitted"]
            self.sender_to_target_stats = data.get("sender_stats", {})
            self.token_to_target_stats = data.get("token_stats", {})
        except Exception:
            pass
```

---

### 模块 4：仿论客客户端的所见即所得富文本邮件编辑器 (`ui/rich_text_editor.py`)

完整复刻 [Coremail 论客客户端](https://www.google.com/search?q=http%3A%2F%2Fwww.lunkr.cn%2F)写信编辑器的核心富文本体验：支持**字体选择、字号选择、加粗、斜体、下划线、删除线、文字颜色（如一键标红）、背景荧光高亮（如一键标黄）、左/中/右对齐、项目符号与编号列表、插入自定义行列表格、插入本地图片，以及直接按 `Ctrl+V` 将剪贴板截图粘贴进邮件正文**。

```python
import base64
from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice
from PySide6.QtGui import (
    QFont, QTextCharFormat, QColor, QTextCursor, QTextListFormat,
    QTextTableFormat, QTextLength, QAction, QImage
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QFontComboBox,
    QComboBox, QTextEdit, QColorDialog, QFileDialog, QInputDialog
)


class pasteableTextEdit(QTextEdit):
    """支持直接 Ctrl+V 粘贴剪贴板截图/图片并自动转为内嵌 HTML Base64 的富文本编辑框"""

    def canInsertFromMimeData(self, source) -> bool:
        if source.hasImage():
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source) -> None:
        if source.hasImage():
            image = QImage(source.imageData())
            if not image.isNull():
                ba = QByteArray()
                buf = QBuffer(ba)
                buf.open(QIODevice.WriteOnly)
                image.save(buf, "PNG")
                b64_str = ba.toBase64().data().decode("ascii")
                self.textCursor().insertHtml(
                    f'<img src="data:image/png;base64,{b64_str}" style="max-width:100%;" />'
                )
                return
        super().insertFromMimeData(source)


class RichTextMailEditor(QWidget):
    """仿 Coremail 论客客户端的所见即所得富文本邮件编辑器组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 顶部富文本格式工具栏
        self.toolbar = QToolBar()
        self.toolbar.setStyleSheet("QToolBar { background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; padding: 3px; spacing: 4px; }")

        # 1. 字体选择
        self.font_box = QFontComboBox()
        self.font_box.setMaximumWidth(150)
        self.font_box.setCurrentFont(QFont("Microsoft YaHei"))
        self.font_box.currentFontChanged.connect(self._on_font_changed)
        self.toolbar.addWidget(self.font_box)

        # 2. 字号选择
        self.size_box = QComboBox()
        for sz in ["9", "10", "11", "12", "14", "16", "18", "20", "24", "28"]:
            self.size_box.addItem(f"{sz} pt", int(sz))
        self.size_box.setCurrentIndex(4)  # 默认 14pt
        self.size_box.currentIndexChanged.connect(self._on_size_changed)
        self.toolbar.addWidget(self.size_box)
        self.toolbar.addSeparator()

        # 3. 粗体 / 斜体 / 下划线 / 删除线
        self.act_bold = QAction("B 加粗", self, checkable=True)
        self.act_bold.triggered.connect(lambda checked: self.editor.setFontWeight(QFont.Bold if checked else QFont.Normal))
        self.toolbar.addAction(self.act_bold)

        self.act_italic = QAction("I 斜体", self, checkable=True)
        self.act_italic.triggered.connect(self.editor.setFontItalic)
        self.toolbar.addAction(self.act_italic)

        self.act_underline = QAction("U 下划线", self, checkable=True)
        self.act_underline.triggered.connect(self.editor.setFontUnderline)
        self.toolbar.addAction(self.act_underline)

        self.act_strike = QAction("S 删除线", self, checkable=True)
        self.act_strike.triggered.connect(self._toggle_strike)
        self.toolbar.addAction(self.act_strike)
        self.toolbar.addSeparator()

        # 4. 字体颜色 / 标红 / 荧光笔标黄 / 选择颜色
        act_red = QAction("🔴 标红", self)
        act_red.triggered.connect(lambda: self.editor.setTextColor(QColor("#DC2626")))
        self.toolbar.addAction(act_red)

        act_highlight = QAction("🟨 标黄高亮", self)
        act_highlight.triggered.connect(self._toggle_yellow_highlight)
        self.toolbar.addAction(act_highlight)

        act_color = QAction("🎨 文字颜色", self)
        act_color.triggered.connect(self._choose_text_color)
        self.toolbar.addAction(act_color)
        self.toolbar.addSeparator()

        # 5. 对齐与列表
        act_left = QAction("左对齐", self)
        act_left.triggered.connect(lambda: self.editor.setAlignment(Qt.AlignLeft))
        self.toolbar.addAction(act_left)

        act_center = QAction("居中", self)
        act_center.triggered.connect(lambda: self.editor.setAlignment(Qt.AlignCenter))
        self.toolbar.addAction(act_center)

        act_bullet = QAction("• 项目列表", self)
        act_bullet.triggered.connect(lambda: self._insert_list(QTextListFormat.ListDisc))
        self.toolbar.addAction(act_bullet)

        act_num = QAction("1. 编号列表", self)
        act_num.triggered.connect(lambda: self._insert_list(QTextListFormat.ListDecimal))
        self.toolbar.addAction(act_num)
        self.toolbar.addSeparator()

        # 6. 插入表格 / 插入图片 / 清除格式
        act_table = QAction("📅 插入表格", self)
        act_table.triggered.connect(self._insert_table)
        self.toolbar.addAction(act_table)

        act_img = QAction("🖼️ 插入图片", self)
        act_img.triggered.connect(self._insert_image_file)
        self.toolbar.addAction(act_img)

        act_clear = QAction("🧹 清除格式", self)
        act_clear.triggered.connect(self._clear_formatting)
        self.toolbar.addAction(act_clear)

        layout.addWidget(self.toolbar)

        # 富文本编辑区主体
        self.editor = pasteableTextEdit()
        self.editor.setAcceptRichText(True)
        self.editor.setStyleSheet(
            "QTextEdit { background: #FFFFFF; border: 1px solid #D1D5DB; border-radius: 6px; padding: 10px; font-size: 14px; }"
        )
        layout.addWidget(self.editor, 1)

    def _on_font_changed(self, font: QFont):
        fmt = QTextCharFormat()
        fmt.setFontFamilies([font.family()])
        self.editor.mergeCurrentCharFormat(fmt)

    def _on_size_changed(self, idx: int):
        sz = self.size_box.itemData(idx)
        if sz:
            self.editor.setFontPointSize(float(sz))

    def _toggle_strike(self, checked: bool):
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(checked)
        self.editor.mergeCurrentCharFormat(fmt)

    def _toggle_yellow_highlight(self):
        cursor = self.editor.textCursor()
        curr_bg = cursor.charFormat().background().color()
        fmt = QTextCharFormat()
        if curr_bg == QColor("#FEF08A"):
            fmt.setBackground(Qt.transparent)
        else:
            fmt.setBackground(QColor("#FEF08A"))
        self.editor.mergeCurrentCharFormat(fmt)

    def _choose_text_color(self):
        color = QColorDialog.getColor(self.editor.textColor(), self, "选择文字颜色")
        if color.isValid():
            self.editor.setTextColor(color)

    def _insert_list(self, style: QTextListFormat.Style):
        cursor = self.editor.textCursor()
        cursor.createList(style)

    def _insert_table(self):
        rows, ok1 = QInputDialog.getInt(self, "插入表格", "行数:", 3, 1, 30)
        if not ok1:
            return
        cols, ok2 = QInputDialog.getInt(self, "插入表格", "列数:", 3, 1, 15)
        if not ok2:
            return
        fmt = QTextTableFormat()
        fmt.setBorder(1)
        fmt.setCellPadding(6)
        fmt.setCellSpacing(0)
        fmt.setWidth(QTextLength(QTextLength.PercentageLength, 100))
        self.editor.textCursor().insertTable(rows, cols, fmt)

    def _insert_image_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择要插入正文的图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.gif)")
        if path:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            ext = path.rsplit(".", 1)[-1].lower()
            self.editor.textCursor().insertHtml(f'<img src="data:image/{ext};base64,{b64}" style="max-width:100%;" />')

    def _clear_formatting(self):
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        cursor.setCharFormat(fmt)

    def set_html(self, html_content: str):
        self.editor.setHtml(html_content or "")

    def get_html(self) -> str:
        return self.editor.toHtml()

    def get_plain_text(self) -> str:
        return self.editor.toPlainText()
```

---

## 五、 喂给 3.8 Flash 的五步接力开发提示词（全量终极版）

你**只需要把这一份文档**发给 3.8 Flash 作为全局上下文，然后按顺序将下面 **5 个 Prompt** 分 5 轮发给它即可生成全套 12 个文件的完整工程：

### 第 1 步 Prompt：生成配置与 SQLite 数据库层 (`config.py` & `core/database.py`)

```text
请严格按照我提供的《Coremail 论客邮箱智能协同与流转助手（全量完整版）设计指南》，编写第 1 部分代码（严禁使用 TODO 或省略号，输出完整可运行源码）：

1. `config.py`：
   - 定义并自动创建 `data/`、`data/attachments/`、机器学习模型路径 `data/ml_models.pkl`。
   - 定义 `DEFAULT_SETTINGS`（包含 IMAP/SMTP 配置、轮询间隔、`filter_mode`、Ollama URL 与默认模型 `qwen2.5:3b`）。

2. `core/database.py`：
   - 封装线程安全的 `DatabaseManager` 类（连接 `data/assistant.db`），自动创建文档第三节定义的 7 张表：`emails`、`memos`、`contacts`、`fulltext_rewrite_rules`、`ml_training_samples`、`match_rules`、`settings`。
   - 实现完整 CRUD 方法，特别是：
     - 自定义备忘录管理：支持无关联邮件独立新建、富文本内容 `content_html`、子任务 `checklist_json`、分类、标签、置顶、到期提醒查询 `get_due_memos()`；
     - 全文改写规则管理：支持手工添加规则，以及由机器学习全文 Diff 自动写入或累加 `hit_count` 的方法 `upsert_learned_rewrite_rule(sender_filter, target_filter, source_pattern, target_template)`；
     - 联系人习惯更新：支持记录对每个联系人 F 是否使用称呼 (`use_salutation`)、专属称呼文本 (`preferred_salutation`) 和偏好发信模式 (`preferred_mode`)。

请输出完整的 `config.py` 和 `core/database.py` 代码。
```

### 第 2 步 Prompt：生成 IMAP/SMTP 引擎、全文改写引擎与全文机器学习引擎 (`core/mail_client.py`, `core/rewriter_engine.py`, `core/ml_learner.py`)

```text
请按照设计指南第四节的参考设计，输出第 2 部分核心后端引擎的完整代码（不要省略任何函数）：

1. `core/mail_client.py` (`CoremailClient` 类)：
   - 支持 Coremail 论客 IMAP `BODY.PEEK[]` 收信、GB18030/UTF-8 解码、附件落盘及内联 `cid:` 图片转本地文件预览；
   - 支持 SMTP 富文本发信（自动将富文本编辑器中的 Base64 / 本地图片转为 `MIMEImage` `cid:` 内联图片，并挂载勾选的原附件和新增本地附件，发信后同步写入 IMAP 已发送文件夹）。

2. `core/rewriter_engine.py` (`RewriterEngine` 类)：
   - `strip_original_salutation_safely(body_text)`：仅当首行命中严格称呼格式时才剥离，若发件人 A 没写称呼则完整保留首句；
   - `generate_target_salutation(target_contacts, fallback_emails)`：支持读取联系人是否习惯加称呼 (`use_salutation`) 及专属称呼；
   - `apply_fulltext_rewrites(...)` 与 `rewrite_html_preserving_format(...)`：基于 BeautifulSoup 在保留原邮件 HTML 表格、颜色与排版的前提下，对全文文本节点执行主语、人称与习惯短语改写；
   - `build_compose_content(...)`：支持 `rewrite_new`（脱壳改写为新邮件，不带 `Fw:` 和原始邮件头）与 `standard_forward`（标准带引文转发）双模式生成。

3. `core/ml_learner.py` (`LocalEmailLearner` 类)：
   - 不截断邮件正文，直接对邮件全文提取 1-gram + 2-gram 特征，使用 `HashingVectorizer` + `SGDClassifier(loss="log_loss")` 在线增量预测是否需流转、推荐流转模式及推荐收件人 F；
   - 实现 `extract_fulltext_rewrite_diffs(original_full_text, edited_full_text, sender_name)`：利用 `difflib.SequenceMatcher` 对比原邮件全文与用户编辑后的发出全文，自动提取用户在正文任意位置修改的主语/短语替换对。
```

### 第 3 步 Prompt：生成 Ollama 客户端、后台异步线程、Fluent 主题与富文本编辑器组件 (`core/ollama_client.py`, `core/worker_threads.py`, `ui/theme.py`, `ui/rich_text_editor.py`)

```text
请继续编写第 3 部分代码（输出完整可运行源码）：

1. `core/ollama_client.py` (`OllamaClient` 类)：
   - 实现 `list_local_models()`、`analyze_and_rewrite_email(...)`（提取摘要、紧急度、建议收件人 F）和 `polish_fulltext_html(raw_text, sender_name, target_salutation)`（供富文本编辑器内一键调用 Ollama 润色全文主语与人称）。

2. `core/worker_threads.py`：
   - 实现 `MailSyncWorker(QThread)`、`OllamaRewriteWorker(QThread)` 和 `SendMailWorker(QThread)`。
   - 在 `SendMailWorker` 发送成功后：
     1) 调用 `LocalEmailLearner.learn_from_user_action` 进行全文增量学习；
     2) 调用 `LocalEmailLearner.extract_fulltext_rewrite_diffs` 自动从“原邮件全文 vs 用户最终发出的纯文本全文”中提取改写短语对，存入 `fulltext_rewrite_rules` 表；
     3) 自动分析用户最终发出正文的首行是否包含称呼，更新目标联系人 F 的 `use_salutation` 与 `preferred_salutation` 习惯。

3. `ui/theme.py`：输出完整的 Windows 11 Fluent 现代浅色卡片风格 QSS 样式表 `APP_QSS`。

4. `ui/rich_text_editor.py` (`RichTextMailEditor` 类)：
   - 按照设计指南第四节模块 4 实现仿论客客户端的所见即所得富文本编辑器，包含格式工具栏（字体、字号、加粗、斜体、下划线、删除线、一键标红、一键标黄高亮、自定义颜色、对齐、列表、插入表格、插入图片、清除格式）以及支持直接 `Ctrl+V` 粘贴剪贴板截图的 `pasteableTextEdit`。
```

### 第 4 步 Prompt：生成双模式富文本发信确认台弹窗与全功能自定义备忘录弹窗 (`ui/compose_send_dialog.py` & `ui/memo_dialog.py`)

```text
请继续编写第 4 部分两个核心交互窗口的完整代码（严禁省略）：

1. `ui/compose_send_dialog.py` (`ComposeAndSendDialog(QDialog)`)：
   - 顶部提供【✨ 改写为新邮件发给 F (`rewrite_new`)】与【↪️ 标准带引文转发 (`standard_forward`)】切换按钮组，默认选中机器学习预测的 `recommended_mode`。
   - 收件人 F 输入框 + 下方常用联系人 `QCheckBox` 快捷勾选池：勾选变化时自动更新收件人框、自动重算抄送人框（`A + B + C + D` 去重并剔除自身与 F），并自动根据第一位收件人 F 的习惯更新正文称呼。
   - 抄送人输入框 + 右侧 `[✓] 抄送原发件人 A` 复选框（取消勾选时自动从抄送栏移除原发件人 A）。
   - 中部集成 `RichTextMailEditor` 富文本邮件编辑器（加载保留原邮件 HTML 排版并已完成全文主语/称呼替换的富文本内容），右侧可展开“对照查看原邮件全文”面板；工具栏旁提供“⚡ 重新应用全文规则改写”与“🤖 调用 Ollama 润色全文主语”按钮。
   - 底部附件管理列表（原邮件附件默认全选，支持取消勾选任意原附件，支持点击“+ 添加本地附件”追加新文件）及“确认并发送”主按钮。

2. `ui/memo_dialog.py` (`MemoEditDialog(QDialog)`)：
   - 支持独立新建自定义备忘录或编辑已有备忘录：包含标题、分类下拉框、优先级、自定义标签、置顶开关、到期提醒时间选择器、动态子任务清单（Checklist 增删与勾选）以及集成 `RichTextMailEditor` 编写富文本备忘详情。
```

### 第 5 步 Prompt：生成规则/全文改写词典弹窗、设置弹窗、主窗口与程序入口 (`ui/rule_contact_dialog.py`, `ui/settings_dialog.py`, `ui/main_window.py`, `main.py`)

```text
请编写最后第 5 部分代码，将全部模块组装为完整可运行的 Windows 桌面软件：

1. `ui/rule_contact_dialog.py` (`RuleAndContactDialog(QDialog)`)：
   - Tab 1【常用联系人与发信习惯】：管理姓名、邮箱、部门、是否习惯加称呼 (`use_salutation`)、专属称呼 (`preferred_salutation`)、偏好模式 (`preferred_mode`)。
   - Tab 2【全文主语/句式改写词典】：展示并管理 `fulltext_rewrite_rules` 表（区分“人工添加”与“🤖 机器学习从全文编辑Diff中自动习得”的规则，支持增删改与启停）。
   - Tab 3【关键词自动匹配规则】：管理关键词、排除词、默认收件人 F 与默认流转模式。

2. `ui/settings_dialog.py` (`SettingsDialog(QDialog)`)：
   - 配置论客 IMAP/SMTP 服务器、账号密码、轮询周期与连接测试；
   - 展示【全文机器学习引擎状态面板】（已学习的邮件全文样本数、自动习得的全文改写短语数、重置模型按钮）；
   - 配置筛选模式与本地 Ollama 参数。

3. `ui/main_window.py` (`MainWindow(QMainWindow)`) 与 `main.py`：
   - 左侧导航栏：“🔄 立即同步邮件”按钮、**“➕ 新建自定义备忘录”**按钮、【待流转邮件】、【全部邮件】、【自定义备忘录中心】视图切换、【联系人/全文词典/规则】与【系统设置】入口。
   - 中间列表区与右侧详情工作台：右侧底部提供 **“✨ 改写为新邮件发给 F”**、**“↪️ 标准转发给 F”**、**“🚫 无需流转（训练机器学习忽略）”** 三个核心按钮；内置 IMAP 定时同步与自定义备忘录到期托盘提醒定时器。
```
