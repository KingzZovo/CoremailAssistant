"""Dual-mode Rich Text Compose and Send Confirmation Dialog.
Supports Rewrite as New vs Standard Forward, F contacts pool, CC auto-computation,
RichTextMailEditor integration, original mail comparison panel, and attachment management.
"""

import os
from typing import Dict, Any, List, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QButtonGroup, QSplitter, QTextEdit,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QProgressBar, QGroupBox, QScrollArea, QWidget
)

from core.database import DatabaseManager
from core.rewriter_engine import RewriterEngine
from core.worker_threads import SendMailWorker, OllamaRewriteWorker
from .rich_text_editor import RichTextMailEditor


class ComposeAndSendDialog(QDialog):
    """双模式发信确认台弹窗"""

    def __init__(self, email_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.email_data = email_data
        self.db = DatabaseManager()
        self.settings = self.db.get_all_settings()
        self.contacts = self.db.get_all_contacts(frequent_only=False)
        self.custom_rules = self.db.get_all_rewrite_rules(enabled_only=True)

        self.contact_checkboxes: Dict[str, QCheckBox] = {}
        self.local_attachments: List[str] = []
        self.send_worker: Optional[SendMailWorker] = None
        self.ollama_worker: Optional[OllamaRewriteWorker] = None

        self.setWindowTitle("邮件智能协同与流转确认台 - CoremailAssistant")
        self.resize(1100, 800)
        self._init_ui()
        self._load_initial_data()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)

        # 1. 顶部流转模式切换按钮组
        mode_box = QHBoxLayout()
        mode_box.addWidget(QLabel("<b>流转模式：</b>"))

        self.mode_btn_group = QButtonGroup(self)
        self.btn_mode_rewrite = QPushButton("✨ 改写为新邮件发给 F (rewrite_new)")
        self.btn_mode_rewrite.setCheckable(True)
        self.btn_mode_forward = QPushButton("↪️ 标准带引文转发 (standard_forward)")
        self.btn_mode_forward.setCheckable(True)

        self.mode_btn_group.addButton(self.btn_mode_rewrite, 1)
        self.mode_btn_group.addButton(self.btn_mode_forward, 2)
        mode_box.addWidget(self.btn_mode_rewrite)
        mode_box.addWidget(self.btn_mode_forward)
        mode_box.addStretch()

        self.mode_btn_group.idClicked.connect(self._on_mode_changed)
        main_layout.addLayout(mode_box)

        # 2. 收件人与常用联系人快捷点选池
        to_group = QGroupBox("收件人 (F) 与常用联系人点选池")
        to_layout = QVBoxLayout(to_group)
        to_layout.setContentsMargins(10, 10, 10, 10)
        to_layout.setSpacing(6)

        to_input_box = QHBoxLayout()
        to_input_box.addWidget(QLabel("收件人："))
        self.to_edit = QLineEdit()
        self.to_edit.setPlaceholderText("可手动输入多个邮箱（英文分号或逗号分隔），或直接勾选下方常用联系人")
        self.to_edit.textChanged.connect(self._on_to_input_edited)
        to_input_box.addWidget(self.to_edit)
        to_layout.addLayout(to_input_box)

        # 联系人勾选池 (带水平滚动的 ScrollArea)
        contacts_scroll = QScrollArea()
        contacts_scroll.setWidgetResizable(True)
        contacts_scroll.setFixedHeight(60)
        contacts_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        contacts_widget = QWidget()
        self.contacts_layout = QHBoxLayout(contacts_widget)
        self.contacts_layout.setContentsMargins(0, 0, 0, 0)
        self.contacts_layout.setSpacing(12)

        for c in self.contacts:
            email_addr = c.get("email", "").strip()
            name = c.get("name") or email_addr.split("@")[0]
            cb = QCheckBox(f"{name} ({email_addr})")
            cb.stateChanged.connect(self._on_contact_checkbox_toggled)
            self.contact_checkboxes[email_addr.lower()] = cb
            self.contacts_layout.addWidget(cb)

        self.contacts_layout.addStretch()
        contacts_scroll.setWidget(contacts_widget)
        to_layout.addWidget(contacts_scroll)
        main_layout.addWidget(to_group)

        # 3. 抄送人栏与原发件人独立控制
        cc_box = QHBoxLayout()
        cc_box.addWidget(QLabel("抄送人："))
        self.cc_edit = QLineEdit()
        self.cc_edit.setPlaceholderText("自动聚合原发件人、原收件人与原抄送人")
        cc_box.addWidget(self.cc_edit, 1)

        self.chk_include_sender = QCheckBox(f"抄送原发件人 A ({self.email_data.get('sender_name') or self.email_data.get('sender_email')})")
        self.chk_include_sender.setChecked(self.settings.get("default_include_sender_in_cc", "1") == "1")
        self.chk_include_sender.stateChanged.connect(self._recompute_recipients)
        cc_box.addWidget(self.chk_include_sender)
        main_layout.addLayout(cc_box)

        # 4. 主题栏
        subj_box = QHBoxLayout()
        subj_box.addWidget(QLabel("主　题："))
        self.subject_edit = QLineEdit()
        subj_box.addWidget(self.subject_edit, 1)

        # 辅助功能按钮
        self.btn_reapply_rules = QPushButton("⚡ 重新应用改写规则")
        self.btn_reapply_rules.clicked.connect(self._reapply_rewrite_rules)
        subj_box.addWidget(self.btn_reapply_rules)

        self.btn_ollama_polish = QPushButton("🤖 Ollama 深度润色")
        self.btn_ollama_polish.clicked.connect(self._call_ollama_polish)
        subj_box.addWidget(self.btn_ollama_polish)

        self.btn_toggle_orig = QPushButton("👁️ 对照原邮件")
        self.btn_toggle_orig.setCheckable(True)
        self.btn_toggle_orig.clicked.connect(self._toggle_orig_panel)
        subj_box.addWidget(self.btn_toggle_orig)

        main_layout.addLayout(subj_box)

        # 5. 中间分割区：左侧所见即所得编辑器，右侧原邮件只读对照面板
        self.splitter = QSplitter(Qt.Horizontal)

        # 左侧富文本邮件编辑器
        self.editor = RichTextMailEditor(self)
        self.splitter.addWidget(self.editor)

        # 右侧原邮件只读对照面板
        self.orig_panel = QWidget()
        orig_layout = QVBoxLayout(self.orig_panel)
        orig_layout.setContentsMargins(4, 0, 0, 0)
        orig_layout.addWidget(QLabel("<b>【原邮件只读对照】</b>"))
        self.orig_text_view = QTextEdit()
        self.orig_text_view.setReadOnly(True)
        self.orig_text_view.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0;")
        orig_layout.addWidget(self.orig_text_view)
        self.orig_panel.setVisible(False)
        self.splitter.addWidget(self.orig_panel)

        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        main_layout.addWidget(self.splitter, 1)

        # 6. 底部附件管理列表
        attach_box = QHBoxLayout()
        attach_box.addWidget(QLabel("<b>附件管理：</b>"))
        self.attach_list = QListWidget()
        self.attach_list.setFixedHeight(64)
        self.attach_list.setStyleSheet("QListWidget { border: 1px solid #E2E8F0; }")
        attach_box.addWidget(self.attach_list, 1)

        btn_add_att = QPushButton("➕ 添加本地附件")
        btn_add_att.clicked.connect(self._add_local_attachment)
        attach_box.addWidget(btn_add_att)
        main_layout.addLayout(attach_box)

        # 7. 发送状态进度与确认按钮栏
        bottom_bar = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_lbl = QLabel()
        bottom_bar.addWidget(self.progress_bar, 1)
        bottom_bar.addWidget(self.status_lbl, 2)

        bottom_bar.addStretch()
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_cancel)

        self.btn_send = QPushButton("🚀 确认并发送")
        self.btn_send.setObjectName("btn_primary")
        self.btn_send.setProperty("primary", True)
        self.btn_send.clicked.connect(self._confirm_and_send)
        bottom_bar.addWidget(self.btn_send)

        main_layout.addLayout(bottom_bar)

    def _get_current_mode(self) -> str:
        return "rewrite_new" if self.btn_mode_rewrite.isChecked() else "standard_forward"

    def _load_initial_data(self):
        # 1. 选中推荐模式
        rec_mode = self.email_data.get("recommended_mode", "rewrite_new")
        if rec_mode == "standard_forward":
            self.btn_mode_forward.setChecked(True)
        else:
            self.btn_mode_rewrite.setChecked(True)

        # 2. 勾选推荐收件人
        suggested_to = self.email_data.get("suggested_to", [])
        if suggested_to:
            for s_addr in suggested_to:
                clean_s = s_addr.strip().lower()
                if clean_s in self.contact_checkboxes:
                    self.contact_checkboxes[clean_s].setChecked(True)
            self.to_edit.setText("; ".join(suggested_to))

        # 3. 原邮件对照展示
        orig_body = self.email_data.get("body_text", "")
        self.orig_text_view.setPlainText(
            f"发件人: {self.email_data.get('sender_name')} <{self.email_data.get('sender_email')}>\n"
            f"时间: {self.email_data.get('date_str')}\n"
            f"主题: {self.email_data.get('subject')}\n\n"
            f"{orig_body}"
        )

        # 4. 加载原邮件附件 (默认全选)
        for att in self.email_data.get("attachments", []):
            item = QListWidgetItem(f"📎 {att.get('filename')} ({att.get('size', 0) // 1024} KB)")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, att.get("filepath"))
            self.attach_list.addItem(item)

        # 5. 初始化计算发信内容与收发人
        self._recompute_recipients()
        self._generate_composed_content()

    def _on_mode_changed(self):
        self._generate_composed_content()

    def _on_contact_checkbox_toggled(self):
        selected_emails = []
        for em, cb in self.contact_checkboxes.items():
            if cb.isChecked():
                selected_emails.append(em)

        self.to_edit.blockSignals(True)
        self.to_edit.setText("; ".join(selected_emails))
        self.to_edit.blockSignals(False)

        self._recompute_recipients()
        self._generate_composed_content()

    def _on_to_input_edited(self):
        raw_text = self.to_edit.text()
        emails = [e.strip().lower() for e in raw_text.replace(",", ";").split(";") if e.strip()]

        for em, cb in self.contact_checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(em in emails)
            cb.blockSignals(False)

        self._recompute_recipients()
        self._generate_composed_content()

    def _get_selected_f_emails(self) -> List[str]:
        raw_text = self.to_edit.text()
        return [e.strip() for e in raw_text.replace(",", ";").split(";") if "@" in e]

    def _recompute_recipients(self):
        my_email = self.settings.get("email_account", "")
        sender_email = self.email_data.get("sender_email", "")
        orig_to = self.email_data.get("to_list", [])
        orig_cc = self.email_data.get("cc_list", [])
        selected_f = self._get_selected_f_emails()
        include_sender = self.chk_include_sender.isChecked()

        _, new_cc = RewriterEngine.compute_recipients(
            my_email=my_email,
            sender_email=sender_email,
            to_list=orig_to,
            cc_list=orig_cc,
            selected_f_emails=selected_f,
            include_sender_in_cc=include_sender
        )

        self.cc_edit.setText("; ".join(new_cc))

    def _generate_composed_content(self):
        mode = self._get_current_mode()
        selected_f = self._get_selected_f_emails()
        target_contacts = [c for c in self.contacts if c.get("email", "").lower() in [f.lower() for f in selected_f]]

        content = RewriterEngine.build_compose_content(
            mode=mode,
            email_data=self.email_data,
            target_contacts=target_contacts,
            selected_f_emails=selected_f,
            custom_rewrite_rules=self.custom_rules
        )

        self.subject_edit.setText(content["subject"])
        if content.get("html_body"):
            self.editor.set_html(content["html_body"])
        else:
            self.editor.set_plain_text(content.get("plain_body", ""))

    def _reapply_rewrite_rules(self):
        self.custom_rules = self.db.get_all_rewrite_rules(enabled_only=True)
        self._generate_composed_content()
        self.status_lbl.setText("已重新应用最新全文改写规则")

    def _call_ollama_polish(self):
        selected_f = self._get_selected_f_emails()
        target_contacts = [c for c in self.contacts if c.get("email", "").lower() in [f.lower() for f in selected_f]]
        sal = RewriterEngine.generate_target_salutation(target_contacts, selected_f)
        sender_name = self.email_data.get("sender_name") or self.email_data.get("sender_email", "")
        raw_text = self.editor.get_plain_text()

        self.btn_ollama_polish.setEnabled(False)
        self.status_lbl.setText("正在调用本地 Ollama 深度润色中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self.ollama_worker = OllamaRewriteWorker(raw_text, sender_name, sal, self)
        self.ollama_worker.rewrite_done.connect(self._on_ollama_done)
        self.ollama_worker.rewrite_failed.connect(self._on_ollama_failed)
        self.ollama_worker.start()

    def _on_ollama_done(self, polished_text: str):
        self.btn_ollama_polish.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_lbl.setText("Ollama 润色完成！")
        self.editor.set_plain_text(polished_text)

    def _on_ollama_failed(self, err_msg: str):
        self.btn_ollama_polish.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_lbl.setText(f"Ollama 润色未完成: {err_msg}")
        QMessageBox.warning(self, "Ollama 润色提示", err_msg)

    def _toggle_orig_panel(self, checked: bool):
        self.orig_panel.setVisible(checked)

    def _add_local_attachment(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择要追加的本地附件")
        if paths:
            for p in paths:
                fname = os.path.basename(p)
                sz = os.path.getsize(p) // 1024
                item = QListWidgetItem(f"📎 [本地新增] {fname} ({sz} KB)")
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                item.setData(Qt.UserRole, p)
                self.attach_list.addItem(item)

    def _confirm_and_send(self):
        to_addrs = self._get_selected_f_emails()
        if not to_addrs:
            QMessageBox.warning(self, "发信校验", "请至少指定一位收件人 F")
            return

        cc_raw = self.cc_edit.text()
        cc_addrs = [c.strip() for c in cc_raw.replace(",", ";").split(";") if "@" in c]
        subject = self.subject_edit.text().strip()
        if not subject:
            QMessageBox.warning(self, "发信校验", "邮件主题不能为空")
            return

        # 收集勾选的附件路径
        final_attachments = []
        for i in range(self.attach_list.count()):
            item = self.attach_list.item(i)
            if item.checkState() == Qt.Checked:
                path = item.data(Qt.UserRole)
                if path and os.path.isfile(path):
                    final_attachments.append(path)

        html_body = self.editor.get_html()
        plain_body = self.editor.get_plain_text()
        mode = self._get_current_mode()

        # 禁用操作按钮，防止重复提交
        self.btn_send.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_lbl.setText("正在发信并执行自学习闭环...")

        self.send_worker = SendMailWorker(
            to_addrs=to_addrs,
            cc_addrs=cc_addrs,
            subject=subject,
            html_body=html_body,
            plain_body=plain_body,
            attachment_paths=final_attachments,
            original_email_data=self.email_data,
            mode=mode,
            parent=self
        )
        self.send_worker.send_progress.connect(lambda msg: self.status_lbl.setText(msg))
        self.send_worker.send_success.connect(self._on_send_success)
        self.send_worker.send_failed.connect(self._on_send_failed)
        self.send_worker.start()

    def _on_send_success(self):
        self.progress_bar.setVisible(False)
        QMessageBox.information(self, "流转完成", "邮件已成功发出，相关改写短语已自动自学习并写入词典！")
        self.accept()

    def _on_send_failed(self, err_msg: str):
        self.btn_send.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_lbl.setText("发送失败")
        QMessageBox.critical(self, "发信失败", err_msg)
