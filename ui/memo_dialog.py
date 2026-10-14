"""Full-featured Custom Memo and Checklist Dialog.
Supports independent memo creation, category, tags, priority, pinning, due reminders,
dynamic multi-step checklists, and RichTextMailEditor integration.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from PySide6.QtCore import Qt, QDateTime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QCheckBox, QPushButton, QDateTimeEdit,
    QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
    QGroupBox, QWidget, QSplitter
)

from core.database import DatabaseManager
from .rich_text_editor import RichTextMailEditor


class MemoEditDialog(QDialog):
    """全功能自定义备忘录编辑/新建弹窗"""

    def __init__(self, memo_data: Optional[Dict[str, Any]] = None, email_uid: str = "", parent=None):
        super().__init__(parent)
        self.memo_data = memo_data or {}
        self.memo_id = self.memo_data.get("id")
        self.email_uid = email_uid or self.memo_data.get("email_uid", "")
        self.db = DatabaseManager()

        title_prefix = "编辑备忘录" if self.memo_id else "新建自定义备忘录"
        self.setWindowTitle(f"{title_prefix} - CoremailAssistant")
        self.resize(850, 700)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # 1. 标题与分类属性栏
        title_box = QHBoxLayout()
        title_box.addWidget(QLabel("<b>标题：</b>"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("请输入备忘录标题...")
        title_box.addWidget(self.title_edit, 1)
        layout.addLayout(title_box)

        attr_box = QHBoxLayout()
        attr_box.addWidget(QLabel("分类："))
        self.category_box = QComboBox()
        self.category_box.setEditable(True)
        for cat in ["日常协调", "个人备忘", "重点跟进", "会议纪要", "财务对账", "系统运维"]:
            self.category_box.addItem(cat)
        attr_box.addWidget(self.category_box)

        attr_box.addWidget(QLabel("优先级："))
        self.priority_box = QComboBox()
        self.priority_box.addItems(["高", "中", "低"])
        self.priority_box.setCurrentText("中")
        attr_box.addWidget(self.priority_box)

        attr_box.addWidget(QLabel("标签："))
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("多个标签用逗号分隔")
        attr_box.addWidget(self.tags_edit, 1)

        self.chk_pinned = QCheckBox("📌 置顶")
        attr_box.addWidget(self.chk_pinned)

        self.chk_done = QCheckBox("✓ 已完成")
        attr_box.addWidget(self.chk_done)
        layout.addLayout(attr_box)

        # 2. 到期提醒时间选择栏
        remind_box = QHBoxLayout()
        self.chk_remind = QCheckBox("⏰ 到期托盘气泡提醒：")
        self.chk_remind.stateChanged.connect(self._toggle_remind_time)
        remind_box.addWidget(self.chk_remind)

        self.time_edit = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.time_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.time_edit.setCalendarPopup(True)
        self.time_edit.setEnabled(False)
        remind_box.addWidget(self.time_edit)
        remind_box.addStretch()
        layout.addLayout(remind_box)

        # 3. 中部分割：左侧子任务步骤 Checklist，右侧富文本详情
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：子任务步骤清单
        checklist_group = QGroupBox("子任务清单 (Checklist)")
        chk_layout = QVBoxLayout(checklist_group)
        self.checklist_widget = QListWidget()
        chk_layout.addWidget(self.checklist_widget)

        btn_box = QHBoxLayout()
        btn_add_step = QPushButton("➕ 添加步骤")
        btn_add_step.clicked.connect(self._add_checklist_item)
        btn_del_step = QPushButton("🗑️ 删除步骤")
        btn_del_step.clicked.connect(self._remove_checklist_item)
        btn_box.addWidget(btn_add_step)
        btn_box.addWidget(btn_del_step)
        chk_layout.addLayout(btn_box)

        splitter.addWidget(checklist_group)

        # 右侧：富文本备忘内容编辑器
        content_group = QGroupBox("富文本详情备忘")
        cnt_layout = QVBoxLayout(content_group)
        self.editor = RichTextMailEditor(self)
        cnt_layout.addWidget(self.editor)
        splitter.addWidget(content_group)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        # 4. 底部按钮栏
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("💾 保存备忘录")
        self.btn_save.setObjectName("btn_primary")
        self.btn_save.setProperty("primary", True)
        self.btn_save.clicked.connect(self._save_memo)
        bottom_bar.addWidget(self.btn_save)

        layout.addLayout(bottom_bar)

    def _toggle_remind_time(self, state):
        self.time_edit.setEnabled(self.chk_remind.isChecked())

    def _add_checklist_item(self):
        text, ok = QInputDialog.getText(self, "添加子任务", "步骤内容描述:")
        if ok and text.strip():
            item = QListWidgetItem(text.strip())
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
            item.setCheckState(Qt.Unchecked)
            self.checklist_widget.addItem(item)

    def _remove_checklist_item(self):
        row = self.checklist_widget.currentRow()
        if row >= 0:
            self.checklist_widget.takeItem(row)

    def _load_data(self):
        if not self.memo_data:
            return

        self.title_edit.setText(self.memo_data.get("title", ""))
        self.category_box.setCurrentText(self.memo_data.get("category", "日常协调"))
        self.priority_box.setCurrentText(self.memo_data.get("priority", "中"))
        self.tags_edit.setText(self.memo_data.get("tags", ""))
        self.chk_pinned.setChecked(bool(self.memo_data.get("is_pinned", 0)))
        self.chk_done.setChecked(bool(self.memo_data.get("is_done", 0)))

        remind_at = self.memo_data.get("remind_at", "")
        if remind_at:
            self.chk_remind.setChecked(True)
            self.time_edit.setEnabled(True)
            dt = QDateTime.fromString(remind_at, "yyyy-MM-dd HH:mm")
            if dt.isValid():
                self.time_edit.setDateTime(dt)

        # 加载 checklist
        checklist = self.memo_data.get("checklist", [])
        for step in checklist:
            text = step.get("text", "")
            done = step.get("done", False)
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
            item.setCheckState(Qt.Checked if done else Qt.Unchecked)
            self.checklist_widget.addItem(item)

        # 加载富文本详情
        content_html = self.memo_data.get("content_html", "")
        self.editor.set_html(content_html)

    def _save_memo(self):
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "保存校验", "备忘录标题不能为空")
            return

        category = self.category_box.currentText().strip() or "日常协调"
        priority = self.priority_box.currentText()
        tags = self.tags_edit.text().strip()
        is_pinned = 1 if self.chk_pinned.isChecked() else 0
        is_done = 1 if self.chk_done.isChecked() else 0
        remind_at = self.time_edit.dateTime().toString("yyyy-MM-dd HH:mm") if self.chk_remind.isChecked() else ""
        content_html = self.editor.get_html()

        # 收集 Checklist
        checklist = []
        for i in range(self.checklist_widget.count()):
            item = self.checklist_widget.item(i)
            checklist.append({
                "text": item.text().strip(),
                "done": item.checkState() == Qt.Checked
            })

        if self.memo_id:
            # 更新已有备忘录
            self.db.update_memo(
                self.memo_id,
                title=title,
                content_html=content_html,
                checklist_json=checklist,
                category=category,
                tags=tags,
                priority=priority,
                is_pinned=is_pinned,
                is_done=is_done,
                remind_at=remind_at
            )
        else:
            # 新建备忘录
            self.db.create_memo(
                title=title,
                content_html=content_html,
                email_uid=self.email_uid,
                checklist=checklist,
                category=category,
                tags=tags,
                priority=priority,
                is_pinned=is_pinned,
                remind_at=remind_at
            )

        self.accept()
