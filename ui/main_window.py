"""Main Window for CoremailAssistant.
Features 3-column workbench (Left navigation, Center email/memo list, Right details & workflow actions),
background auto-sync, due memo tray notifications, and full ML/Rewrite loop.
"""

import os
from datetime import datetime
from typing import Dict, Any, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QTextEdit,
    QSplitter, QMessageBox, QSystemTrayIcon, QMenu, QStatusBar,
    QProgressBar, QGroupBox, QButtonGroup, QAbstractItemView
)

from core.database import DatabaseManager
from core.ml_learner import LocalEmailLearner
from core.worker_threads import MailSyncWorker
from .compose_send_dialog import ComposeAndSendDialog
from .memo_dialog import MemoEditDialog
from .rule_contact_dialog import RuleAndContactDialog
from .settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    """Coremail 论客邮箱智能流转与协同助手三栏式主工作台窗口"""

    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.learner = LocalEmailLearner()

        self.current_view = "pending"  # "pending", "all_emails", "memos"
        self.selected_email: Optional[Dict[str, Any]] = None
        self.selected_memo: Optional[Dict[str, Any]] = None
        self.sync_worker: Optional[MailSyncWorker] = None

        self.setWindowTitle("CoremailAssistant - 论客邮箱智能协同与邮件处理助手 (Windows 版)")
        self.resize(1260, 840)

        self._init_ui()
        self._setup_tray()
        self._setup_timers()
        self._refresh_current_view()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # -------------------------------------------------------------
        # 1. 左侧导航边栏 (Width ~210)
        # -------------------------------------------------------------
        nav_panel = QWidget()
        nav_panel.setFixedWidth(220)
        nav_panel.setStyleSheet("background-color: #F1F5F9; border-right: 1px solid #E2E8F0;")
        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(12, 16, 12, 16)
        nav_layout.setSpacing(8)

        # 软件标识
        logo_lbl = QLabel("📬 Coremail助手")
        logo_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #1E3A8A; margin-bottom: 6px;")
        nav_layout.addWidget(logo_lbl)

        # 核心快捷操作按钮
        self.btn_sync_now = QPushButton("🔄 立即同步收信")
        self.btn_sync_now.setObjectName("btn_primary")
        self.btn_sync_now.setProperty("primary", True)
        self.btn_sync_now.clicked.connect(self._start_manual_sync)
        nav_layout.addWidget(self.btn_sync_now)

        self.btn_new_memo = QPushButton("➕ 新建自定义备忘")
        self.btn_new_memo.clicked.connect(self._create_independent_memo)
        nav_layout.addWidget(self.btn_new_memo)

        nav_layout.addSpacing(10)

        # 视图切换单选按钮组
        self.nav_btn_group = QButtonGroup(self)
        self.btn_view_pending = QPushButton("📥 待流转协同")
        self.btn_view_pending.setCheckable(True)
        self.btn_view_pending.setChecked(True)

        self.btn_view_all = QPushButton("📑 全部历史邮件")
        self.btn_view_all.setCheckable(True)

        self.btn_view_memos = QPushButton("📝 自定义备忘录")
        self.btn_view_memos.setCheckable(True)

        self.nav_btn_group.addButton(self.btn_view_pending, 1)
        self.nav_btn_group.addButton(self.btn_view_all, 2)
        self.nav_btn_group.addButton(self.btn_view_memos, 3)
        self.nav_btn_group.idClicked.connect(self._on_nav_view_changed)

        nav_layout.addWidget(self.btn_view_pending)
        nav_layout.addWidget(self.btn_view_all)
        nav_layout.addWidget(self.btn_view_memos)

        nav_layout.addStretch()

        # 底部配置工具入口
        self.btn_open_rules = QPushButton("👥 联系人与改写词典")
        self.btn_open_rules.clicked.connect(self._open_rules_dialog)
        nav_layout.addWidget(self.btn_open_rules)

        self.btn_open_settings = QPushButton("⚙️ 系统与邮箱设置")
        self.btn_open_settings.clicked.connect(self._open_settings_dialog)
        nav_layout.addWidget(self.btn_open_settings)

        main_layout.addWidget(nav_panel)

        # -------------------------------------------------------------
        # 2. 中间列表区 与 3. 右侧详情工作台 (Splitter)
        # -------------------------------------------------------------
        self.splitter = QSplitter(Qt.Horizontal)

        # 中间：项目列表
        mid_widget = QWidget()
        mid_layout = QVBoxLayout(mid_widget)
        mid_layout.setContentsMargins(12, 14, 12, 14)
        mid_layout.setSpacing(8)

        search_box = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索主题、发件人或内容...")
        self.search_input.textChanged.connect(self._refresh_current_view)
        search_box.addWidget(self.search_input)
        mid_layout.addLayout(search_box)

        self.item_list = QListWidget()
        self.item_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.item_list.currentItemChanged.connect(self._on_item_selected)
        mid_layout.addWidget(self.item_list)

        self.splitter.addWidget(mid_widget)

        # 右侧：详情与流转工作台
        self.right_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_widget)
        self.right_layout.setContentsMargins(14, 14, 14, 14)
        self.right_layout.setSpacing(10)

        # 邮件/备忘录详情头部信息卡片
        self.detail_header_lbl = QLabel("请在左侧列表中选择一项以查看详细内容")
        self.detail_header_lbl.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; line-height: 1.6;"
        )
        self.detail_header_lbl.setTextFormat(Qt.RichText)
        self.right_layout.addWidget(self.detail_header_lbl)

        # 详情正文展示区域
        self.detail_body_view = QTextEdit()
        self.detail_body_view.setReadOnly(True)
        self.detail_body_view.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px;")
        self.right_layout.addWidget(self.detail_body_view, 1)

        # 底部动作操作台 (邮件模式下)
        self.mail_actions_group = QGroupBox("⚡ 邮件智能协同与流转工作台")
        act_layout = QHBoxLayout(self.mail_actions_group)
        act_layout.setContentsMargins(10, 10, 10, 10)

        self.btn_rewrite_new = QPushButton("✨ 改写为新邮件发给 F")
        self.btn_rewrite_new.setObjectName("btn_primary")
        self.btn_rewrite_new.setProperty("primary", True)
        self.btn_rewrite_new.clicked.connect(lambda: self._open_compose_dialog("rewrite_new"))
        act_layout.addWidget(self.btn_rewrite_new)

        self.btn_forward = QPushButton("↪️ 标准带引文转发给 F")
        self.btn_forward.clicked.connect(lambda: self._open_compose_dialog("standard_forward"))
        act_layout.addWidget(self.btn_forward)

        self.btn_create_memo_from_mail = QPushButton("📌 转为备忘录")
        self.btn_create_memo_from_mail.clicked.connect(self._create_memo_from_email)
        act_layout.addWidget(self.btn_create_memo_from_mail)

        self.btn_ignore = QPushButton("🚫 无需流转 (训练忽略)")
        self.btn_ignore.setObjectName("btn_danger")
        self.btn_ignore.setProperty("danger", True)
        self.btn_ignore.clicked.connect(self._ignore_email)
        act_layout.addWidget(self.btn_ignore)

        self.right_layout.addWidget(self.mail_actions_group)

        # 底部动作操作台 (备忘录模式下)
        self.memo_actions_group = QGroupBox("📝 备忘录操作")
        memo_act_layout = QHBoxLayout(self.memo_actions_group)
        self.btn_edit_memo = QPushButton("✏️ 编辑备忘录详情")
        self.btn_edit_memo.clicked.connect(self._edit_current_memo)
        memo_act_layout.addWidget(self.btn_edit_memo)

        self.btn_toggle_memo_done = QPushButton("✓ 切换完成状态")
        self.btn_toggle_memo_done.clicked.connect(self._toggle_current_memo_done)
        memo_act_layout.addWidget(self.btn_toggle_memo_done)

        self.btn_del_memo = QPushButton("🗑️ 删除备忘录")
        self.btn_del_memo.setObjectName("btn_danger")
        self.btn_del_memo.setProperty("danger", True)
        self.btn_del_memo.clicked.connect(self._delete_current_memo)
        memo_act_layout.addWidget(self.btn_del_memo)
        memo_act_layout.addStretch()

        self.memo_actions_group.setVisible(False)
        self.right_layout.addWidget(self.memo_actions_group)

        self.splitter.addWidget(self.right_widget)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 6)

        main_layout.addWidget(self.splitter, 1)

        # 底部状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.sync_progress = QProgressBar()
        self.sync_progress.setMaximumWidth(180)
        self.sync_progress.setVisible(False)
        self.status_bar.addPermanentWidget(self.sync_progress)
        self.status_bar.showMessage("就绪")

    def _setup_tray(self):
        """配置 Windows 任务栏系统托盘与气泡提醒"""
        from PySide6.QtWidgets import QStyle
        self.tray = QSystemTrayIcon(self)
        icon = self.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray.setIcon(icon)
        self.tray.setToolTip("CoremailAssistant 论客邮箱智能助手")

        tray_menu = QMenu()
        act_show = QAction("显示主窗口", self)
        act_show.triggered.connect(self.showNormal)
        tray_menu.addAction(act_show)

        act_sync = QAction("立即检查邮件", self)
        act_sync.triggered.connect(self._start_manual_sync)
        tray_menu.addAction(act_sync)

        tray_menu.addSeparator()
        act_exit = QAction("退出程序", self)
        act_exit.triggered.connect(self.close)
        tray_menu.addAction(act_exit)

        self.tray.setContextMenu(tray_menu)
        self.tray.show()

    def _setup_timers(self):
        """启动后台定时器：邮件自动轮询与备忘录到期检测"""
        # 1. 备忘录到期检测定时器 (每 30 秒)
        self.memo_timer = QTimer(self)
        self.memo_timer.timeout.connect(self._check_due_memos)
        self.memo_timer.start(30000)

        # 2. 邮件自动拉取定时器
        settings = self.db.get_all_settings()
        interval_secs = int(settings.get("poll_interval", 60) or 60)
        self.mail_timer = QTimer(self)
        self.mail_timer.timeout.connect(self._start_background_sync)
        self.mail_timer.start(max(15, interval_secs) * 1000)

    def _on_nav_view_changed(self, btn_id: int):
        if btn_id == 1:
            self.current_view = "pending"
        elif btn_id == 2:
            self.current_view = "all_emails"
        elif btn_id == 3:
            self.current_view = "memos"
        self._refresh_current_view()

    def _refresh_current_view(self):
        kw = self.search_input.text().strip() or None
        self.item_list.clear()

        if self.current_view in ("pending", "all_emails"):
            self.mail_actions_group.setVisible(True)
            self.memo_actions_group.setVisible(False)
            is_matched_only = (self.current_view == "pending")
            status_filter = "pending" if self.current_view == "pending" else None

            emails = self.db.get_all_emails(
                limit=150,
                status_filter=status_filter,
                is_matched_only=is_matched_only,
                keyword=kw
            )

            # 更新未读徽标计数
            pending_count = len(self.db.get_pending_emails())
            self.btn_view_pending.setText(f"📥 待流转协同 ({pending_count})")

            for em in emails:
                item = QListWidgetItem()
                status_tag = ""
                st = em.get("status")
                if st == "sent_new":
                    status_tag = " [✨已改写发出]"
                elif st == "forwarded":
                    status_tag = " [↪️已转发]"
                elif st == "ignored":
                    status_tag = " [🚫已忽略]"
                elif em.get("is_matched") == 1:
                    status_tag = f" [{em.get('matched_rule_name') or '推荐流转'}]"

                sender_name = em.get("sender_name") or em.get("sender_email")
                item.setText(f"{em.get('subject')}{status_tag}\n来自: {sender_name} | {em.get('date_str')}")
                item.setData(Qt.UserRole, em)
                self.item_list.addItem(item)

        elif self.current_view == "memos":
            self.mail_actions_group.setVisible(False)
            self.memo_actions_group.setVisible(True)

            memos = self.db.get_memos(keyword=kw)
            for m in memos:
                item = QListWidgetItem()
                pin_tag = "📌 " if m.get("is_pinned") else ""
                done_tag = "[已完成] " if m.get("is_done") else ""
                remind_tag = f" ⏰{m.get('remind_at')}" if m.get("remind_at") else ""
                item.setText(f"{pin_tag}{done_tag}【{m.get('category')}】{m.get('title')}{remind_tag}\n优先级: {m.get('priority')} | 标签: {m.get('tags') or '无'}")
                item.setData(Qt.UserRole, m)
                self.item_list.addItem(item)

        if self.item_list.count() > 0:
            self.item_list.setCurrentRow(0)
        else:
            self._clear_detail()

    def _on_item_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]):
        if not current:
            self._clear_detail()
            return

        data = current.data(Qt.UserRole)
        if not data:
            return

        if self.current_view in ("pending", "all_emails"):
            self.selected_email = data
            self.selected_memo = None
            self._display_email_detail(data)
        elif self.current_view == "memos":
            self.selected_memo = data
            self.selected_email = None
            self._display_memo_detail(data)

    def _display_email_detail(self, em: Dict[str, Any]):
        to_names = ", ".join([f"{x.get('name')}<{x.get('email')}>" for x in em.get("to_list", [])])
        cc_names = ", ".join([f"{x.get('name')}<{x.get('email')}>" for x in em.get("cc_list", [])])
        rec_f = ", ".join(em.get("suggested_to", [])) or "暂无推荐收件人"

        header_html = f"""
        <div style="font-size:15px; font-weight:700; color:#1E3A8A; margin-bottom:6px;">{em.get('subject')}</div>
        <b>发件人：</b>{em.get('sender_name')} &lt;{em.get('sender_email')}&gt;<br>
        <b>发送时间：</b>{em.get('date_str')}<br>
        <b>原收件人：</b>{to_names}<br>
        <b>原抄送人：</b>{cc_names or '无'}<br>
        <b>推荐收件人 (F)：</b><span style="color:#2563EB; font-weight:600;">{rec_f}</span> |
        <b>推荐模式：</b>{'✨ 改写为新邮件' if em.get('recommended_mode') == 'rewrite_new' else '↪️ 标准带引文转发'}
        """

        if em.get("ai_summary"):
            header_html += f"<div style='margin-top:6px; background:#EFF6FF; padding:6px 10px; border-radius:6px; color:#1E40AF;'><b>🤖 核心摘要：</b>{em.get('ai_summary')}</div>"

        att_list = em.get("attachments", [])
        if att_list:
            att_names = ", ".join([f"📎 {a.get('filename')}" for a in att_list])
            header_html += f"<div style='margin-top:4px;'><b>附件列表：</b>{att_names}</div>"

        self.detail_header_lbl.setText(header_html)

        if em.get("body_html"):
            self.detail_body_view.setHtml(em.get("body_html"))
        else:
            self.detail_body_view.setPlainText(em.get("body_text", ""))

    def _display_memo_detail(self, m: Dict[str, Any]):
        chk_lines = []
        for c in m.get("checklist", []):
            box = "☑️" if c.get("done") else "⬜"
            chk_lines.append(f"{box} {c.get('text')}")
        chk_text = "<br>".join(chk_lines) if chk_lines else "暂无子任务"

        header_html = f"""
        <div style="font-size:15px; font-weight:700; color:#0F766E; margin-bottom:6px;">【{m.get('category')}】{m.get('title')}</div>
        <b>优先级：</b>{m.get('priority')} | <b>置顶：</b>{'是' if m.get('is_pinned') else '否'} | <b>状态：</b>{'已完成' if m.get('is_done') else '进行中'}<br>
        <b>到期提醒时间：</b>{m.get('remind_at') or '未设置'}<br>
        <b>子任务清单：</b><br>{chk_text}
        """
        self.detail_header_lbl.setText(header_html)
        self.detail_body_view.setHtml(m.get("content_html", "") or "<p style='color:#9CA3AF;'>暂无详情内容</p>")

    def _clear_detail(self):
        self.detail_header_lbl.setText("请在左侧列表中选择一项以查看详细内容")
        self.detail_body_view.clear()

    # =========================================================================
    # 同步与流转业务动作
    # =========================================================================

    def _start_manual_sync(self):
        self._start_email_sync(is_manual=True)

    def _start_background_sync(self):
        self._start_email_sync(is_manual=False)

    def _start_email_sync(self, is_manual: bool = False):
        if self.sync_worker and self.sync_worker.isRunning():
            if is_manual:
                self.status_bar.showMessage("邮件同步已在后台执行中...", 3000)
            return

        self.sync_progress.setVisible(True)
        self.sync_progress.setRange(0, 0)
        self.btn_sync_now.setEnabled(False)

        self.sync_worker = MailSyncWorker(self)
        self.sync_worker.progress_msg.connect(lambda msg: self.status_bar.showMessage(msg))
        self.sync_worker.sync_finished.connect(self._on_sync_finished)
        self.sync_worker.sync_failed.connect(self._on_sync_failed)
        self.sync_worker.start()

    def _on_sync_finished(self, count: int, new_emails: list):
        self.sync_progress.setVisible(False)
        self.btn_sync_now.setEnabled(True)
        self.status_bar.showMessage(f"邮件检查完成，拉取到 {count} 封新邮件", 4000)
        self._refresh_current_view()

        if count > 0:
            self.tray.showMessage(
                "Coremail 邮件通知",
                f"收到 {count} 封新邮件，系统已自动完成智能流转初筛！",
                QSystemTrayIcon.Information,
                5000
            )

    def _on_sync_failed(self, err_msg: str):
        self.sync_progress.setVisible(False)
        self.btn_sync_now.setEnabled(True)
        self.status_bar.showMessage(f"同步失败: {err_msg}", 5000)

    def _check_due_memos(self):
        """检查是否有到期未提醒的备忘录，并在 Windows 系统托盘弹出气泡通知"""
        due_list = self.db.get_due_memos()
        for m in due_list:
            self.tray.showMessage(
                f"⏰ 备忘录到期提醒: {m.get('title')}",
                f"分类: {m.get('category')} | 优先级: {m.get('priority')}\n请及时跟进处理！",
                QSystemTrayIcon.Warning,
                8000
            )
            self.db.mark_memo_reminded(m["id"])

    def _open_compose_dialog(self, mode: str):
        if not self.selected_email:
            QMessageBox.information(self, "操作提示", "请先在列表中选中一封邮件")
            return
        data = dict(self.selected_email)
        data["recommended_mode"] = mode
        dlg = ComposeAndSendDialog(data, self)
        if dlg.exec():
            self._refresh_current_view()

    def _ignore_email(self):
        if not self.selected_email:
            return
        subj = self.selected_email.get("subject")
        if QMessageBox.question(self, "无需流转", f"确定将邮件【{subj}】标记为无需流转吗？\n（系统将记录此操作训练机器学习模型）") == QMessageBox.Yes:
            self.db.update_email_status(self.selected_email["uid"], "ignored")
            # 训练负样本
            self.learner.learn_from_user_action(
                email_data=self.selected_email,
                action_label=0
            )
            self.db.save_training_sample(
                email_uid=self.selected_email["uid"],
                sender_email=self.selected_email.get("sender_email", ""),
                subject=subj,
                full_body_text=self.selected_email.get("body_text", ""),
                final_sent_text="",
                action_label=0,
                chosen_mode="",
                chosen_to_emails=[],
                chosen_cc_emails=[]
            )
            self._refresh_current_view()

    def _create_memo_from_email(self):
        if not self.selected_email:
            return
        subj = self.selected_email.get("subject", "")
        body_html = self.selected_email.get("body_html") or f"<p>{self.selected_email.get('body_text', '')}</p>"
        dlg = MemoEditDialog(
            memo_data={
                "title": f"跟进：{subj}",
                "content_html": body_html,
                "category": "日常协调",
                "priority": "中"
            },
            email_uid=self.selected_email.get("uid", ""),
            parent=self
        )
        if dlg.exec():
            QMessageBox.information(self, "提示", "已成功将邮件转为备忘录！")

    def _create_independent_memo(self):
        dlg = MemoEditDialog(parent=self)
        if dlg.exec():
            if self.current_view == "memos":
                self._refresh_current_view()

    def _edit_current_memo(self):
        if not self.selected_memo:
            return
        dlg = MemoEditDialog(memo_data=self.selected_memo, parent=self)
        if dlg.exec():
            self._refresh_current_view()

    def _toggle_current_memo_done(self):
        if not self.selected_memo:
            return
        new_done = 0 if self.selected_memo.get("is_done") else 1
        self.db.update_memo(self.selected_memo["id"], is_done=new_done)
        self._refresh_current_view()

    def _delete_current_memo(self):
        if not self.selected_memo:
            return
        title = self.selected_memo.get("title")
        if QMessageBox.question(self, "删除备忘录", f"确定删除备忘录【{title}】吗？") == QMessageBox.Yes:
            self.db.delete_memo(self.selected_memo["id"])
            self._refresh_current_view()

    def _open_rules_dialog(self):
        dlg = RuleAndContactDialog(self)
        dlg.exec()

    def _open_settings_dialog(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            # 刷新轮询间隔
            settings = self.db.get_all_settings()
            interval_secs = int(settings.get("poll_interval", 60) or 60)
            self.mail_timer.setInterval(max(15, interval_secs) * 1000)
