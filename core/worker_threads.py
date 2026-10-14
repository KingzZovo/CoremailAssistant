"""Background worker threads for asynchronous email sync, ML/Ollama prediction, and SMTP sending."""

import re
from typing import List, Dict, Any, Optional
from PySide6.QtCore import QThread, Signal

from .database import DatabaseManager
from .mail_client import CoremailClient
from .ml_learner import LocalEmailLearner
from .rewriter_engine import STRICT_SALUTATION_REGEX
from .ollama_client import OllamaClient


class MailSyncWorker(QThread):
    """后台异步邮件同步与智能化初筛工作线程"""

    progress_msg = Signal(str)
    sync_finished = Signal(int, list)  # (新拉取邮件数, 新邮件列表)
    sync_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.db = DatabaseManager()
        self.learner = LocalEmailLearner()

    def run(self):
        try:
            settings = self.db.get_all_settings()
            email_account = settings.get("email_account", "").strip()
            email_pwd = settings.get("email_password", "")

            if not email_account or not email_pwd:
                self.sync_failed.emit("未配置论客邮箱账号或密码，请先在系统设置中保存配置")
                return

            self.progress_msg.emit(f"正在连接论客邮箱服务器: {settings.get('imap_host')}...")
            client = CoremailClient(settings)

            existing_uids = self.db.get_existing_uids()
            max_fetch = int(settings.get("max_fetch_count", 30) or 30)

            self.progress_msg.emit("正在扫描收件箱最新邮件...")
            new_emails = client.fetch_new_emails(existing_uids, max_fetch=max_fetch)

            if not new_emails:
                self.progress_msg.emit("检查完毕，没有发现新邮件")
                self.sync_finished.emit(0, [])
                return

            self.progress_msg.emit(f"拉取到 {len(new_emails)} 封新邮件，正在执行智能流转分析...")

            contacts = self.db.get_all_contacts()
            match_rules = self.db.get_all_match_rules(enabled_only=True)
            filter_mode = settings.get("filter_mode", "rules_and_ml")

            ollama_client = None
            if settings.get("ollama_enabled") == "1":
                ollama_client = OllamaClient(
                    base_url=settings.get("ollama_url", "http://127.0.0.1:11434"),
                    default_model=settings.get("ollama_model", "qwen2.5:3b"),
                    timeout=int(settings.get("ollama_timeout", 30) or 30)
                )

            processed_emails = []

            for em in new_emails:
                is_matched = 0
                ml_confidence = 0.0
                matched_rule_name = ""
                recommended_mode = "rewrite_new"
                suggested_to = []
                ai_summary = ""
                ai_urgency = "普通"

                subj = em.get("subject", "")
                body = em.get("body_text", "")
                full_search_text = f"{subj} {body}"

                # 1. 规则引擎优先匹配 (若包含 rules_and_ml 或 rules_only)
                if filter_mode in ("rules_and_ml", "rules_only"):
                    for rule in match_rules:
                        scope = rule.get("match_scope", "both")
                        target_text = subj if scope == "subject" else (body if scope == "body" else full_search_text)
                        keywords = [k.strip() for k in rule.get("keywords", "").split(",") if k.strip()]
                        exclude_kw = [k.strip() for k in rule.get("exclude_keywords", "").split(",") if k.strip()]

                        # 检查排除词
                        if any(ex in target_text for ex in exclude_kw):
                            continue

                        # 检查命中词
                        if any(kw in target_text for kw in keywords):
                            is_matched = 1
                            ml_confidence = 1.0
                            matched_rule_name = rule.get("rule_name", "关键词规则")
                            recommended_mode = rule.get("default_send_mode", "rewrite_new")
                            suggested_to = rule.get("target_emails", [])
                            break

                # 2. 本地机器学习增量分析 (若未被规则命中且模式允许)
                if not is_matched and filter_mode in ("rules_and_ml", "ml_only", "ollama_hybrid"):
                    pred = self.learner.predict_email(em, contacts)
                    ml_confidence = pred.get("need_action_prob", 0.0)
                    if pred.get("is_ml_recommended", False):
                        is_matched = 1
                        matched_rule_name = "🤖 全文机器学习智能推荐"
                        recommended_mode = pred.get("recommended_mode", "rewrite_new")
                        suggested_to = pred.get("predicted_f_emails", [])

                # 3. 本地 Ollama 混合分析与摘要
                if ollama_client and ollama_client.is_available() and is_matched:
                    try:
                        ai_res = ollama_client.analyze_and_rewrite_email(em, contacts)
                        ai_summary = ai_res.get("summary", "")
                        ai_urgency = ai_res.get("urgency", "普通")
                        if not suggested_to and ai_res.get("suggested_contacts"):
                            suggested_to = ai_res.get("suggested_contacts")
                    except Exception:
                        pass

                em["is_matched"] = is_matched
                em["ml_confidence"] = ml_confidence
                em["matched_rule_name"] = matched_rule_name
                em["recommended_mode"] = recommended_mode
                em["suggested_to"] = suggested_to
                em["ai_summary"] = ai_summary
                em["ai_urgency"] = ai_urgency

                # 写入 SQLite 数据库
                self.db.insert_email(em)
                processed_emails.append(em)

            self.progress_msg.emit(f"同步完成！新增 {len(processed_emails)} 封邮件")
            self.sync_finished.emit(len(processed_emails), processed_emails)

        except Exception as e:
            self.sync_failed.emit(f"同步邮件失败: {str(e)}")


class OllamaRewriteWorker(QThread):
    """调用本地 Ollama 对邮件全文进行主语/人称润色的异步线程"""

    rewrite_done = Signal(str)
    rewrite_failed = Signal(str)

    def __init__(self, raw_text: str, sender_name: str, salutation: str, parent=None):
        super().__init__(parent)
        self.raw_text = raw_text
        self.sender_name = sender_name
        self.salutation = salutation
        self.db = DatabaseManager()

    def run(self):
        try:
            settings = self.db.get_all_settings()
            client = OllamaClient(
                base_url=settings.get("ollama_url", "http://127.0.0.1:11434"),
                default_model=settings.get("ollama_model", "qwen2.5:3b"),
                timeout=int(settings.get("ollama_timeout", 30) or 30)
            )
            if not client.is_available():
                self.rewrite_failed.emit("未检测到本地 Ollama 服务，请确认服务已启动 (ollama run qwen2.5:3b)")
                return

            result = client.polish_fulltext_html(
                raw_text=self.raw_text,
                sender_name=self.sender_name,
                target_salutation=self.salutation
            )
            self.rewrite_done.emit(result)
        except Exception as e:
            self.rewrite_failed.emit(f"调用 Ollama 润色异常: {str(e)}")


class SendMailWorker(QThread):
    """
    异步发信工作线程：
    负责 SMTP 发送富文本邮件，并在发送成功后自动执行三大学习与习惯记忆闭环：
    1. LocalEmailLearner 在线增量训练 (learn_from_user_action)
    2. 全文 Diff 差异提取并持久化至 fulltext_rewrite_rules
    3. 目标收件人 F 的称呼习惯与偏好模式自动更新
    """

    send_progress = Signal(str)
    send_success = Signal()
    send_failed = Signal(str)

    def __init__(
        self,
        to_addrs: List[str],
        cc_addrs: List[str],
        subject: str,
        html_body: str,
        plain_body: str,
        attachment_paths: List[str],
        original_email_data: Dict[str, Any],
        mode: str = "rewrite_new",
        parent=None
    ):
        super().__init__(parent)
        self.to_addrs = to_addrs
        self.cc_addrs = cc_addrs
        self.subject = subject
        self.html_body = html_body
        self.plain_body = plain_body
        self.attachment_paths = attachment_paths
        self.orig_data = original_email_data
        self.mode = mode

        self.db = DatabaseManager()
        self.learner = LocalEmailLearner()

    def run(self):
        try:
            settings = self.db.get_all_settings()
            client = CoremailClient(settings)

            self.send_progress.emit("正在连接 Coremail SMTP 服务器发信...")
            client.send_email(
                to_addrs=self.to_addrs,
                cc_addrs=self.cc_addrs,
                subject=self.subject,
                html_body=self.html_body,
                plain_body=self.plain_body,
                attachment_paths=self.attachment_paths,
                save_to_sent=True
            )

            self.send_progress.emit("邮件发送成功！正在执行自学习算法与习惯记忆更新...")

            # -------------------------------------------------------------
            # 闭环 1: LocalEmailLearner 全文特征增量训练
            # -------------------------------------------------------------
            self.learner.learn_from_user_action(
                email_data=self.orig_data,
                action_label=1,
                chosen_mode=self.mode,
                chosen_f_emails=self.to_addrs
            )

            # -------------------------------------------------------------
            # 闭环 2: 全文 Diff 差异自学习 (原邮件全文 vs 用户编辑后发出全文)
            # -------------------------------------------------------------
            orig_full_text = self.orig_data.get("body_text", "")
            sender_name = self.orig_data.get("sender_name") or self.orig_data.get("sender_email", "").split("@")[0]
            target_filter = self.to_addrs[0].lower().strip() if self.to_addrs else ""
            sender_filter = self.orig_data.get("sender_email", "").lower().strip()

            learned_diffs = LocalEmailLearner.extract_fulltext_rewrite_diffs(
                original_full_text=orig_full_text,
                edited_full_text=self.plain_body,
                sender_name=sender_name
            )

            for src_phrase, tgt_phrase in learned_diffs:
                # 写入数据库全文改写词典
                self.db.upsert_learned_rewrite_rule(
                    sender_filter="",
                    target_filter="",
                    source_pattern=src_phrase,
                    target_template=tgt_phrase
                )

            # -------------------------------------------------------------
            # 闭环 3: 学习联系人 F 的专属称呼习惯与偏好模式
            # -------------------------------------------------------------
            first_line = (self.plain_body.strip().splitlines() or [""])[0]
            sal_match = STRICT_SALUTATION_REGEX.match(first_line)

            for f_email in self.to_addrs:
                self.db.increment_contact_send_count(f_email)
                if sal_match:
                    # 用户发信时写了称呼
                    self.db.update_contact_habit(
                        email=f_email,
                        use_salutation=1,
                        preferred_salutation=sal_match.group(0).strip(),
                        preferred_mode=self.mode
                    )
                else:
                    # 用户发信时没有加称呼（直接写事情）
                    self.db.update_contact_habit(
                        email=f_email,
                        use_salutation=0,
                        preferred_mode=self.mode
                    )

            # -------------------------------------------------------------
            # 闭环 4: 记录样本与更新邮件状态
            # -------------------------------------------------------------
            self.db.save_training_sample(
                email_uid=self.orig_data.get("uid", ""),
                sender_email=self.orig_data.get("sender_email", ""),
                subject=self.orig_data.get("subject", ""),
                full_body_text=orig_full_text,
                final_sent_text=self.plain_body,
                action_label=1,
                chosen_mode=self.mode,
                chosen_to_emails=self.to_addrs,
                chosen_cc_emails=self.cc_addrs
            )

            new_status = "sent_new" if self.mode == "rewrite_new" else "forwarded"
            self.db.update_email_status(self.orig_data.get("uid", ""), new_status)

            if settings.get("auto_mark_read") == "1":
                client.mark_email_read(self.orig_data.get("uid", ""))

            self.send_success.emit()

        except Exception as e:
            self.send_failed.emit(f"发送邮件失败: {str(e)}")
