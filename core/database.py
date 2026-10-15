"""SQLite Database access layer for CoremailAssistant.
Encapsulates thread-safe connection management and complete CRUD operations for the 7 core tables.
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import DATABASE_PATH, DEFAULT_SETTINGS


class DatabaseManager:
    """线程安全的 SQLite 数据库管理类，统一管理 7 张核心业务表"""

    _instance: Optional["DatabaseManager"] = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str = DATABASE_PATH):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, db_path: str = DATABASE_PATH):
        if getattr(self, "_initialized", False):
            return
        self.db_path = db_path
        self._op_lock = threading.Lock()
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()
        self._initialized = True

    def get_connection(self) -> sqlite3.Connection:
        """获取配置了 Row 工厂的 SQLite 连接对象"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")  # 提升并发读写性能
        return conn

    def init_db(self) -> None:
        """初始化建表并填入默认配置与种子规则"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. 邮件主表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT UNIQUE NOT NULL,
                message_id TEXT,
                subject TEXT NOT NULL,
                sender_name TEXT,
                sender_email TEXT NOT NULL,
                to_list_json TEXT NOT NULL,
                cc_list_json TEXT NOT NULL,
                date_str TEXT,
                body_text TEXT,
                body_html TEXT,
                attachments_json TEXT DEFAULT '[]',
                is_matched INTEGER DEFAULT 0,
                ml_confidence REAL DEFAULT 0.0,
                matched_rule_name TEXT DEFAULT '',
                recommended_mode TEXT DEFAULT 'rewrite_new',
                ai_summary TEXT DEFAULT '',
                ai_urgency TEXT DEFAULT '普通',
                suggested_to_json TEXT DEFAULT '[]',
                status TEXT DEFAULT 'pending',
                processed_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 2. 全功能自定义备忘录表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS memos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_uid TEXT DEFAULT '',
                title TEXT NOT NULL,
                content_html TEXT DEFAULT '',
                checklist_json TEXT DEFAULT '[]',
                category TEXT DEFAULT '日常协调',
                tags TEXT DEFAULT '',
                priority TEXT DEFAULT '中',
                is_pinned INTEGER DEFAULT 0,
                is_done INTEGER DEFAULT 0,
                remind_at TEXT DEFAULT '',
                is_reminded INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 3. 常用联系人与个人发信习惯记忆表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                department TEXT DEFAULT '',
                preferred_salutation TEXT DEFAULT '',
                use_salutation INTEGER DEFAULT 1,
                preferred_mode TEXT DEFAULT 'auto',
                is_frequent_target INTEGER DEFAULT 1,
                send_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 4. 全文主语、人称与句式改写规则词典表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS fulltext_rewrite_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_filter TEXT DEFAULT '',
                target_filter TEXT DEFAULT '',
                source_pattern TEXT NOT NULL,
                target_template TEXT NOT NULL,
                is_regex INTEGER DEFAULT 0,
                learned_from_diff INTEGER DEFAULT 0,
                hit_count INTEGER DEFAULT 1,
                is_enabled INTEGER DEFAULT 1
            );
            """)

            # 5. 机器学习全文历史训练样本表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS ml_training_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_uid TEXT,
                sender_email TEXT,
                subject TEXT,
                full_body_text TEXT,
                final_sent_text TEXT DEFAULT '',
                action_label INTEGER NOT NULL,
                chosen_mode TEXT DEFAULT '',
                chosen_to_emails_json TEXT DEFAULT '[]',
                chosen_cc_emails_json TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 6. 关键词规则表
            cursor.execute("""
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
            """)

            # 7. 系统配置表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """)

            # 写入默认 settings（如果不存在）
            for k, v in DEFAULT_SETTINGS.items():
                cursor.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?);",
                    (k, str(v)),
                )

            # 写入初始全文改写默认词典（若表中尚无数据）
            cursor.execute("SELECT COUNT(*) FROM fulltext_rewrite_rules;")
            if cursor.fetchone()[0] == 0:
                default_rewrites = [
                    ("麻烦您", "麻烦你"),
                    ("请您协助", "请协助"),
                    ("请您帮忙", "请帮忙"),
                    ("请您确认", "请确认"),
                    ("请您审阅", "请审阅"),
                    ("请您审批", "请审批"),
                    ("请您查收", "请查收"),
                    ("请您知悉", "请知悉"),
                    ("发给您", "同步给你"),
                    ("向您汇报", "同步一下"),
                    ("我这边", "{sender_name}那边"),
                    ("我们这边", "{sender_name}团队那边"),
                    ("我部门", "{sender_name}部门"),
                    ("我科室", "{sender_name}科室"),
                    ("我方", "{sender_name}方"),
                ]
                cursor.executemany(
                    """
                    INSERT INTO fulltext_rewrite_rules
                    (source_pattern, target_template, is_regex, learned_from_diff, hit_count, is_enabled)
                    VALUES (?, ?, 0, 0, 10, 1);
                    """,
                    default_rewrites,
                )

            conn.commit()

    # =========================================================================
    # 1. 系统配置管理 (Settings CRUD)
    # =========================================================================

    def get_setting(self, key: str, default: Any = None) -> Any:
        """获取单个系统配置项"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?;", (key,))
            row = cursor.fetchone()
            if row:
                return row["value"]
            return default if default is not None else DEFAULT_SETTINGS.get(key, "")

    def save_setting(self, key: str, value: Any) -> None:
        """写入或更新单个系统配置项"""
        val_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value;",
                (key, val_str),
            )
            conn.commit()

    set_setting = save_setting

    def get_all_settings(self) -> Dict[str, Any]:
        """获取所有系统配置构成的字典（含默认配置回退）"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings;")
            result = dict(DEFAULT_SETTINGS)
            for row in cursor.fetchall():
                result[row["key"]] = row["value"]
            return result

    get_settings = get_all_settings

    def save_settings(self, settings_dict: Dict[str, Any]) -> None:
        """批量保存更新系统配置"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            for k, v in settings_dict.items():
                val_str = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
                cursor.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value;",
                    (k, val_str),
                )
            conn.commit()

    update_settings = save_settings

    # =========================================================================
    # 2. 邮件数据管理 (Emails CRUD)
    # =========================================================================

    def get_existing_uids(self) -> set:
        """获取数据库中已记录的所有邮件 UID 集合"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT uid FROM emails;")
            return {row["uid"] for row in cursor.fetchall()}

    def insert_email(self, email_data: Dict[str, Any]) -> int:
        """插入新拉取的邮件，若已存在则忽略"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            to_json = (
                json.dumps(email_data.get("to_list", []), ensure_ascii=False)
                if not isinstance(email_data.get("to_list"), str)
                else email_data.get("to_list")
            )
            cc_json = (
                json.dumps(email_data.get("cc_list", []), ensure_ascii=False)
                if not isinstance(email_data.get("cc_list"), str)
                else email_data.get("cc_list")
            )
            attach_json = (
                json.dumps(email_data.get("attachments", []), ensure_ascii=False)
                if not isinstance(email_data.get("attachments"), str)
                else email_data.get("attachments", "[]")
            )
            sugg_to_json = (
                json.dumps(email_data.get("suggested_to", []), ensure_ascii=False)
                if not isinstance(email_data.get("suggested_to"), str)
                else email_data.get("suggested_to", "[]")
            )

            cursor.execute(
                """
                INSERT OR IGNORE INTO emails (
                    uid, message_id, subject, sender_name, sender_email,
                    to_list_json, cc_list_json, date_str, body_text, body_html,
                    attachments_json, is_matched, ml_confidence, matched_rule_name,
                    recommended_mode, ai_summary, ai_urgency, suggested_to_json, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(email_data.get("uid", "")),
                    email_data.get("message_id", ""),
                    email_data.get("subject", ""),
                    email_data.get("sender_name", ""),
                    email_data.get("sender_email", ""),
                    to_json,
                    cc_json,
                    email_data.get("date_str", ""),
                    email_data.get("body_text", ""),
                    email_data.get("body_html", ""),
                    attach_json,
                    int(email_data.get("is_matched", 0)),
                    float(email_data.get("ml_confidence", 0.0)),
                    email_data.get("matched_rule_name", ""),
                    email_data.get("recommended_mode", "rewrite_new"),
                    email_data.get("ai_summary", ""),
                    email_data.get("ai_urgency", "普通"),
                    sugg_to_json,
                    email_data.get("status", "pending"),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_email_by_uid(self, uid: str) -> Optional[Dict[str, Any]]:
        """根据 UID 获取单封完整邮件详情"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM emails WHERE uid = ?;", (str(uid),))
            row = cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            try:
                data["to_list"] = json.loads(data["to_list_json"] or "[]")
                data["cc_list"] = json.loads(data["cc_list_json"] or "[]")
                data["attachments"] = json.loads(data["attachments_json"] or "[]")
                data["suggested_to"] = json.loads(data["suggested_to_json"] or "[]")
            except Exception:
                pass
            return data

    def get_all_emails(
        self,
        limit: int = 200,
        status_filter: Optional[str] = None,
        is_matched_only: bool = False,
        keyword: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """条件检索邮件列表"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            clauses = []
            params: List[Any] = []

            if status_filter:
                clauses.append("status = ?")
                params.append(status_filter)
            if is_matched_only:
                clauses.append("is_matched = 1")
            if keyword:
                clauses.append("(subject LIKE ? OR sender_name LIKE ? OR sender_email LIKE ? OR body_text LIKE ?)")
                pat = f"%{keyword}%"
                params.extend([pat, pat, pat, pat])

            where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            sql = f"SELECT * FROM emails {where_str} ORDER BY id DESC LIMIT ?;"
            params.append(limit)

            cursor.execute(sql, params)
            results = []
            for row in cursor.fetchall():
                d = dict(row)
                try:
                    d["to_list"] = json.loads(d["to_list_json"] or "[]")
                    d["cc_list"] = json.loads(d["cc_list_json"] or "[]")
                    d["attachments"] = json.loads(d["attachments_json"] or "[]")
                    d["suggested_to"] = json.loads(d["suggested_to_json"] or "[]")
                except Exception:
                    pass
                results.append(d)
            return results

    def get_pending_emails(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取所有待流转/待处理的邮件 (is_matched = 1 且 status = 'pending')"""
        return self.get_all_emails(limit=limit, status_filter="pending", is_matched_only=True)

    def update_email_status(self, uid: str, status: str, processed_at: Optional[str] = None) -> None:
        """更新邮件处理状态 (pending / sent_new / forwarded / ignored)"""
        if not processed_at:
            processed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE emails SET status = ?, processed_at = ? WHERE uid = ?;",
                (status, processed_at, str(uid)),
            )
            conn.commit()

    def update_email_prediction(
        self,
        uid: str,
        is_matched: int,
        ml_confidence: float,
        recommended_mode: str,
        suggested_to: List[str],
        matched_rule_name: str = "",
    ) -> None:
        """更新邮件的智能匹配结果与推荐收件人"""
        sugg_json = json.dumps(suggested_to, ensure_ascii=False)
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE emails SET
                    is_matched = ?,
                    ml_confidence = ?,
                    recommended_mode = ?,
                    suggested_to_json = ?,
                    matched_rule_name = ?
                WHERE uid = ?;
                """,
                (
                    is_matched,
                    float(ml_confidence),
                    recommended_mode,
                    sugg_json,
                    matched_rule_name,
                    str(uid),
                ),
            )
            conn.commit()

    def update_email_ai_info(self, uid: str, ai_summary: str, ai_urgency: str = "普通") -> None:
        """更新邮件的大模型/分析摘要与紧急程度"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE emails SET ai_summary = ?, ai_urgency = ? WHERE uid = ?;",
                (ai_summary, ai_urgency, str(uid)),
            )
            conn.commit()

    # =========================================================================
    # 3. 全功能自定义备忘录管理 (Memos CRUD)
    # =========================================================================

    def create_memo(
        self,
        title: str,
        content_html: str = "",
        email_uid: str = "",
        checklist: Optional[List[Dict[str, Any]]] = None,
        category: str = "日常协调",
        tags: str = "",
        priority: str = "中",
        is_pinned: int = 0,
        remind_at: str = "",
    ) -> int:
        """创建备忘录（支持独立脱离邮件创建或关联特定邮件）"""
        chk_json = json.dumps(checklist or [], ensure_ascii=False)
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO memos (
                    email_uid, title, content_html, checklist_json,
                    category, tags, priority, is_pinned, is_done, remind_at, is_reminded
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0);
                """,
                (
                    email_uid,
                    title,
                    content_html,
                    chk_json,
                    category,
                    tags,
                    priority,
                    int(is_pinned),
                    remind_at,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def update_memo(self, memo_id: int, **kwargs) -> bool:
        """动态更新备忘录属性"""
        if not kwargs:
            return False
        allowed_fields = {
            "title", "content_html", "checklist_json", "category",
            "tags", "priority", "is_pinned", "is_done", "remind_at", "is_reminded"
        }
        updates = []
        params = []
        for k, v in kwargs.items():
            if k in allowed_fields:
                updates.append(f"{k} = ?")
                if k == "checklist_json" and not isinstance(v, str):
                    params.append(json.dumps(v, ensure_ascii=False))
                else:
                    params.append(v)

        if not updates:
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(memo_id)

        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            sql = f"UPDATE memos SET {', '.join(updates)} WHERE id = ?;"
            cursor.execute(sql, params)
            conn.commit()
            return cursor.rowcount > 0

    def get_memo_by_id(self, memo_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 查询单个备忘录详情"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM memos WHERE id = ?;", (memo_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d["checklist"] = json.loads(d["checklist_json"] or "[]")
            except Exception:
                d["checklist"] = []
            return d

    def get_memos(
        self,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        is_done: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询备忘录列表（支持置顶优先、按未完成与更新时间排序）"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            clauses = []
            params: List[Any] = []

            if category and category != "全部":
                clauses.append("category = ?")
                params.append(category)
            if tag:
                clauses.append("tags LIKE ?")
                params.append(f"%{tag}%")
            if is_done is not None:
                clauses.append("is_done = ?")
                params.append(int(is_done))
            if keyword:
                clauses.append("(title LIKE ? OR content_html LIKE ?)")
                params.extend([f"%{keyword}%", f"%{keyword}%"])

            where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            sql = f"""
            SELECT * FROM memos
            {where_str}
            ORDER BY is_pinned DESC, is_done ASC, id DESC;
            """
            cursor.execute(sql, params)
            results = []
            for row in cursor.fetchall():
                d = dict(row)
                try:
                    d["checklist"] = json.loads(d["checklist_json"] or "[]")
                except Exception:
                    d["checklist"] = []
                results.append(d)
            return results

    def delete_memo(self, memo_id: int) -> bool:
        """删除备忘录"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memos WHERE id = ?;", (memo_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_due_memos(self, now_str: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询当前或之前已到期、未提醒且未完成的备忘录"""
        if not now_str:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM memos
                WHERE remind_at != '' AND remind_at <= ? AND is_reminded = 0 AND is_done = 0
                ORDER BY remind_at ASC;
                """,
                (now_str,),
            )
            results = []
            for row in cursor.fetchall():
                d = dict(row)
                try:
                    d["checklist"] = json.loads(d["checklist_json"] or "[]")
                except Exception:
                    d["checklist"] = []
                results.append(d)
            return results

    def mark_memo_reminded(self, memo_id: int) -> None:
        """标记备忘录已弹出到期提醒"""
        self.update_memo(memo_id, is_reminded=1)

    # =========================================================================
    # 4. 常用联系人与个人习惯记忆 (Contacts CRUD)
    # =========================================================================

    def get_all_contacts(self, frequent_only: bool = False) -> List[Dict[str, Any]]:
        """获取联系人列表，按发送频次与首字母排序"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            if frequent_only:
                cursor.execute(
                    "SELECT * FROM contacts WHERE is_frequent_target = 1 ORDER BY send_count DESC, id ASC;"
                )
            else:
                cursor.execute("SELECT * FROM contacts ORDER BY send_count DESC, id ASC;")
            return [dict(r) for r in cursor.fetchall()]

    def get_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """根据邮箱地址获取联系人及其称呼习惯"""
        if not email:
            return None
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contacts WHERE LOWER(email) = LOWER(?);", (email.strip(),))
            row = cursor.fetchone()
            return dict(row) if row else None

    def add_contact(
        self,
        name: str,
        email: str,
        department: str = "",
        preferred_salutation: str = "",
        use_salutation: int = 1,
        preferred_mode: str = "auto",
        is_frequent_target: int = 1,
    ) -> int:
        """新增联系人，若已存在则更新基础信息"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO contacts (
                    name, email, department, preferred_salutation,
                    use_salutation, preferred_mode, is_frequent_target, send_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(email) DO UPDATE SET
                    name = excluded.name,
                    department = excluded.department,
                    is_frequent_target = excluded.is_frequent_target;
                """,
                (
                    name.strip(),
                    email.strip().lower(),
                    department.strip(),
                    preferred_salutation.strip(),
                    int(use_salutation),
                    preferred_mode,
                    int(is_frequent_target),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def update_contact(self, contact_id: int, **kwargs) -> bool:
        """更新联系人信息"""
        allowed = {
            "name", "email", "department", "preferred_salutation",
            "use_salutation", "preferred_mode", "is_frequent_target", "send_count"
        }
        updates = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                updates.append(f"{k} = ?")
                params.append(v)

        if not updates:
            return False
        params.append(contact_id)

        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            sql = f"UPDATE contacts SET {', '.join(updates)} WHERE id = ?;"
            cursor.execute(sql, params)
            conn.commit()
            return cursor.rowcount > 0

    def delete_contact(self, contact_id: int) -> bool:
        """删除联系人"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM contacts WHERE id = ?;", (contact_id,))
            conn.commit()
            return cursor.rowcount > 0

    def increment_contact_send_count(self, email: str) -> None:
        """发送成功后递增联系人使用频次"""
        if not email:
            return
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE contacts SET send_count = send_count + 1 WHERE LOWER(email) = LOWER(?);",
                (email.strip(),),
            )
            conn.commit()

    def update_contact_habit(
        self,
        email: str,
        use_salutation: Optional[int] = None,
        preferred_salutation: Optional[str] = None,
        preferred_mode: Optional[str] = None,
        salutation: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> None:
        """由机器学习或发信拦截器自动学习更新对联系人 F 的发信习惯"""
        if not email:
            return
        if salutation is not None and preferred_salutation is None:
            preferred_salutation = salutation
        if mode is not None and preferred_mode is None:
            preferred_mode = mode

        updates = []
        params = []
        if use_salutation is not None:
            updates.append("use_salutation = ?")
            params.append(int(use_salutation))
        if preferred_salutation is not None:
            updates.append("preferred_salutation = ?")
            params.append(preferred_salutation.strip())
        if preferred_mode is not None:
            updates.append("preferred_mode = ?")
            params.append(preferred_mode)

        if not updates:
            return
        params.append(email.strip().lower())

        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            sql = f"UPDATE contacts SET {', '.join(updates)} WHERE LOWER(email) = ?;"
            cursor.execute(sql, params)
            conn.commit()

    # =========================================================================
    # 5. 全文主语/句式改写词典管理 (Fulltext Rewrite Rules CRUD)
    # =========================================================================

    def get_all_rewrite_rules(
        self,
        enabled_only: bool = False,
        sender_email: str = "",
        target_email: str = "",
    ) -> List[Dict[str, Any]]:
        """获取所有全文改写规则，支持启用状态与发件人/收件人范围过滤，按命中使用次数降序排列"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            clauses = []
            params: List[Any] = []
            if enabled_only:
                clauses.append("is_enabled = 1")
            if sender_email:
                clauses.append("(sender_filter = '' OR LOWER(sender_filter) = LOWER(?))")
                params.append(sender_email.strip())
            if target_email:
                clauses.append("(target_filter = '' OR LOWER(target_filter) = LOWER(?))")
                params.append(target_email.strip())
            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            sql = f"SELECT * FROM fulltext_rewrite_rules {where_sql} ORDER BY hit_count DESC, id ASC;"
            cursor.execute(sql, params)
            return [dict(r) for r in cursor.fetchall()]

    get_active_rewrite_rules = get_all_rewrite_rules
    list_rewrite_rules = get_all_rewrite_rules

    def add_rewrite_rule(
        self,
        source_pattern: str,
        target_template: str,
        sender_filter: str = "",
        target_filter: str = "",
        is_regex: int = 0,
        learned_from_diff: int = 0,
        hit_count: int = 1,
        is_enabled: int = 1,
    ) -> int:
        """手动添加全文改写规则"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO fulltext_rewrite_rules (
                    sender_filter, target_filter, source_pattern, target_template,
                    is_regex, learned_from_diff, hit_count, is_enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    sender_filter.strip(),
                    target_filter.strip(),
                    source_pattern.strip(),
                    target_template.strip(),
                    int(is_regex),
                    int(learned_from_diff),
                    int(hit_count),
                    int(is_enabled),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def update_rewrite_rule(self, rule_id: int, **kwargs) -> bool:
        """更新全文改写规则"""
        allowed = {
            "sender_filter", "target_filter", "source_pattern", "target_template",
            "is_regex", "learned_from_diff", "hit_count", "is_enabled"
        }
        updates = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                updates.append(f"{k} = ?")
                params.append(v)
        if not updates:
            return False
        params.append(rule_id)

        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            sql = f"UPDATE fulltext_rewrite_rules SET {', '.join(updates)} WHERE id = ?;"
            cursor.execute(sql, params)
            conn.commit()
            return cursor.rowcount > 0

    def delete_rewrite_rule(self, rule_id: int) -> bool:
        """删除全文改写规则"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM fulltext_rewrite_rules WHERE id = ?;", (rule_id,))
            conn.commit()
            return cursor.rowcount > 0

    def upsert_learned_rewrite_rule(
        self,
        sender_filter: str = "",
        target_filter: str = "",
        source_pattern: str = "",
        target_template: str = "",
        is_regex: int = 0,
    ) -> Tuple[int, bool]:
        """
        核心方法：由机器学习 Diff 对比器在用户编辑发出后调用。
        若存在相同原词 (source_pattern) 且作用范围相同：则递增命中频次 hit_count，并刷新 target_template；
        若不存在：则插入新记录，标记 learned_from_diff = 1。
        返回 (rule_id, is_new_created)。
        """
        clean_src = source_pattern.strip()
        clean_tgt = target_template.strip()
        s_filter = sender_filter.strip()
        t_filter = target_filter.strip()

        if not clean_src or not clean_tgt:
            return 0, False

        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, hit_count FROM fulltext_rewrite_rules
                WHERE source_pattern = ? AND sender_filter = ? AND target_filter = ?;
                """,
                (clean_src, s_filter, t_filter),
            )
            row = cursor.fetchone()
            if row:
                rule_id = row["id"]
                cursor.execute(
                    """
                    UPDATE fulltext_rewrite_rules
                    SET hit_count = hit_count + 1,
                        target_template = ?,
                        is_enabled = 1
                    WHERE id = ?;
                    """,
                    (clean_tgt, rule_id),
                )
                conn.commit()
                return rule_id, False
            else:
                cursor.execute(
                    """
                    INSERT INTO fulltext_rewrite_rules (
                        sender_filter, target_filter, source_pattern, target_template,
                        is_regex, learned_from_diff, hit_count, is_enabled
                    ) VALUES (?, ?, ?, ?, ?, 1, 1, 1);
                    """,
                    (s_filter, t_filter, clean_src, clean_tgt, int(is_regex)),
                )
                conn.commit()
                return cursor.lastrowid, True

    # =========================================================================
    # 6. 机器学习历史训练样本管理 (ML Training Samples)
    # =========================================================================

    def save_training_sample(
        self,
        email_uid: str,
        sender_email: str,
        subject: str,
        full_body_text: str,
        final_sent_text: str,
        action_label: int,
        chosen_mode: str,
        chosen_to_emails: List[str],
        chosen_cc_emails: List[str],
    ) -> int:
        """保存用户流转或忽略操作的全文级完整样本，供在线更新与离线重训练"""
        to_json = json.dumps(chosen_to_emails or [], ensure_ascii=False)
        cc_json = json.dumps(chosen_cc_emails or [], ensure_ascii=False)
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO ml_training_samples (
                    email_uid, sender_email, subject, full_body_text,
                    final_sent_text, action_label, chosen_mode,
                    chosen_to_emails_json, chosen_cc_emails_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(email_uid),
                    sender_email.strip(),
                    subject.strip(),
                    full_body_text,
                    final_sent_text,
                    int(action_label),
                    chosen_mode,
                    to_json,
                    cc_json,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_all_training_samples(self) -> List[Dict[str, Any]]:
        """获取所有历史训练样本"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ml_training_samples ORDER BY id ASC;")
            return [dict(r) for r in cursor.fetchall()]

    def get_sample_count(self) -> int:
        """获取已学习的样本总数"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM ml_training_samples;")
            return cursor.fetchone()[0]

    def get_learned_diff_rules_count(self) -> int:
        """获取从全文 Diff 中自动学习到的规则数量"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM fulltext_rewrite_rules WHERE learned_from_diff = 1;"
            )
            return cursor.fetchone()[0]

    # =========================================================================
    # 7. 关键词自动流转规则管理 (Match Rules CRUD)
    # =========================================================================

    def get_all_match_rules(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """获取关键词流转规则，按 priority 升序排序"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            if enabled_only:
                cursor.execute(
                    "SELECT * FROM match_rules WHERE is_enabled = 1 ORDER BY priority ASC, id ASC;"
                )
            else:
                cursor.execute("SELECT * FROM match_rules ORDER BY priority ASC, id ASC;")
            rows = cursor.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                try:
                    d["target_emails"] = json.loads(d["target_emails_json"] or "[]")
                except Exception:
                    d["target_emails"] = []
                results.append(d)
            return results

    def add_match_rule(
        self,
        rule_name: str,
        keywords: str,
        target_emails: List[str],
        match_scope: str = "both",
        exclude_keywords: str = "",
        default_send_mode: str = "rewrite_new",
        default_comment: str = "请协助处理以下协调事宜：",
        priority: int = 10,
        is_enabled: int = 1,
    ) -> int:
        """添加关键词流转规则"""
        tgt_json = json.dumps(target_emails, ensure_ascii=False)
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO match_rules (
                    rule_name, match_scope, keywords, exclude_keywords,
                    target_emails_json, default_send_mode, default_comment,
                    priority, is_enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    rule_name.strip(),
                    match_scope,
                    keywords.strip(),
                    exclude_keywords.strip(),
                    tgt_json,
                    default_send_mode,
                    default_comment,
                    int(priority),
                    int(is_enabled),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def update_match_rule(self, rule_id: int, **kwargs) -> bool:
        """更新关键词流转规则"""
        allowed = {
            "rule_name", "match_scope", "keywords", "exclude_keywords",
            "target_emails_json", "default_send_mode", "default_comment",
            "priority", "is_enabled"
        }
        updates = []
        params = []
        for k, v in kwargs.items():
            if k == "target_emails":
                updates.append("target_emails_json = ?")
                params.append(json.dumps(v, ensure_ascii=False))
            elif k in allowed:
                updates.append(f"{k} = ?")
                params.append(v)
        if not updates:
            return False
        params.append(rule_id)

        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            sql = f"UPDATE match_rules SET {', '.join(updates)} WHERE id = ?;"
            cursor.execute(sql, params)
            conn.commit()
            return cursor.rowcount > 0

    def delete_match_rule(self, rule_id: int) -> bool:
        """删除关键词流转规则"""
        with self._op_lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM match_rules WHERE id = ?;", (rule_id,))
            conn.commit()
            return cursor.rowcount > 0

    # =========================================================================
    # 8. 跨模块调用兼容别名 (Cross-module Compatibility Aliases)
    # =========================================================================

    # 联系人相关别名
    get_contacts = get_all_contacts
    list_contacts = get_all_contacts
    upsert_contact = add_contact

    # 匹配规则相关别名
    get_rules = get_all_match_rules
    list_rules = get_all_match_rules

    # 邮件存取相关别名
    save_email = insert_email
    get_emails = get_all_emails
    list_emails = get_all_emails
    get_matched_emails = get_pending_emails

    # 备忘录相关别名
    add_memo = create_memo
    save_memo = create_memo
    create_or_update_memo = create_memo
    get_all_memos = get_memos
    list_memos = get_memos

