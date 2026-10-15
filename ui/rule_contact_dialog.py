"""Rule and Contact Management Dialog.
Features:
- Tab 1: Frequent Contacts & Individual Salutation/Mode Habit Memory
- Tab 2: Fulltext Subject/Pronoun Rewrite Dictionary (Manual vs ML-Learned)
- Tab 3: Keyword Auto-Routing Rules
"""

import json
from typing import Dict, Any, List, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QComboBox, QCheckBox, QInputDialog,
    QWidget
)

from core.database import DatabaseManager


class RuleAndContactDialog(QDialog):
    """常用联系人习惯、全文改写词典与流转规则配置管理对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.db = DatabaseManager()
        self.setWindowTitle("联系人发信习惯、改写词典与流转规则管理 - CoremailAssistant")
        self.resize(1000, 650)
        self._init_ui()
        self._load_all_tabs()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)

        self.tabs = QTabWidget()

        # Tab 1: 常用联系人与个人习惯记忆
        self.tab_contacts = QWidget()
        self._setup_contacts_tab(self.tab_contacts)
        self.tabs.addTab(self.tab_contacts, "👥 常用联系人与发信习惯")

        # Tab 2: 全文主语/句式改写规则词典
        self.tab_rewrites = QWidget()
        self._setup_rewrites_tab(self.tab_rewrites)
        self.tabs.addTab(self.tab_rewrites, "📖 全文主语/句式改写词典")

        # Tab 3: 关键词自动匹配流转规则
        self.tab_rules = QWidget()
        self._setup_rules_tab(self.tab_rules)
        self.tabs.addTab(self.tab_rules, "⚡ 关键词自动流转规则")

        layout.addWidget(self.tabs)

        bottom_box = QHBoxLayout()
        bottom_box.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        bottom_box.addWidget(btn_close)
        layout.addLayout(bottom_box)

    # =========================================================================
    # Tab 1: 常用联系人
    # =========================================================================

    def _setup_contacts_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        self.contact_table = QTableWidget(0, 8)
        self.contact_table.setHorizontalHeaderLabels([
            "ID", "姓名", "邮箱", "部门", "加称呼习惯", "专属称呼文本", "偏好模式", "发送频次"
        ])
        self.contact_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.contact_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.contact_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.contact_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.contact_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.contact_table)

        btn_bar = QHBoxLayout()
        btn_add = QPushButton("➕ 添加联系人")
        btn_add.clicked.connect(self._add_contact)
        btn_edit = QPushButton("✏️ 编辑称呼习惯")
        btn_edit.clicked.connect(self._edit_contact)
        btn_del = QPushButton("🗑️ 删除联系人")
        btn_del.clicked.connect(self._delete_contact)

        btn_bar.addWidget(btn_add)
        btn_bar.addWidget(btn_edit)
        btn_bar.addWidget(btn_del)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

    def _load_contacts(self):
        self.contact_table.setRowCount(0)
        contacts = self.db.get_all_contacts()
        for c in contacts:
            row = self.contact_table.rowCount()
            self.contact_table.insertRow(row)
            self.contact_table.setItem(row, 0, QTableWidgetItem(str(c.get("id"))))
            self.contact_table.setItem(row, 1, QTableWidgetItem(c.get("name", "")))
            self.contact_table.setItem(row, 2, QTableWidgetItem(c.get("email", "")))
            self.contact_table.setItem(row, 3, QTableWidgetItem(c.get("department", "")))

            use_sal = "✓ 加称呼" if c.get("use_salutation", 1) == 1 else "✗ 不加称呼"
            self.contact_table.setItem(row, 4, QTableWidgetItem(use_sal))
            self.contact_table.setItem(row, 5, QTableWidgetItem(c.get("preferred_salutation", "")))

            pref_mode = c.get("preferred_mode", "auto")
            mode_map = {"auto": "自动推荐", "rewrite_new": "改写新建", "standard_forward": "标准转发"}
            self.contact_table.setItem(row, 6, QTableWidgetItem(mode_map.get(pref_mode, pref_mode)))
            self.contact_table.setItem(row, 7, QTableWidgetItem(str(c.get("send_count", 0))))

    def _add_contact(self):
        name, ok1 = QInputDialog.getText(self, "添加联系人", "姓名:")
        if not ok1 or not name.strip():
            return
        email, ok2 = QInputDialog.getText(self, "添加联系人", "邮箱地址:")
        if not ok2 or not email.strip():
            return
        dept, _ = QInputDialog.getText(self, "添加联系人", "部门 (可选):")
        sal, _ = QInputDialog.getText(self, "添加联系人", "专属称呼 (例如 '张工，你好：', 留空则系统自动生成):")

        self.db.add_contact(
            name=name.strip(),
            email=email.strip(),
            department=dept.strip(),
            preferred_salutation=sal.strip(),
            use_salutation=1
        )
        self._load_contacts()

    def _edit_contact(self):
        row = self.contact_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "操作提示", "请先在表格中选择一行联系人")
            return
        cid = int(self.contact_table.item(row, 0).text())
        name = self.contact_table.item(row, 1).text()
        sal = self.contact_table.item(row, 5).text()

        new_sal, ok = QInputDialog.getText(self, f"编辑联系人习惯 - {name}", "修改专属称呼（留空表示按姓名生成）：", text=sal)
        if ok:
            use_sal = QMessageBox.question(
                self, "加称呼习惯", f"发信给【{name}】时，是否习惯在正文开头加上称呼？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            ) == QMessageBox.Yes
            self.db.update_contact(
                cid,
                preferred_salutation=new_sal.strip(),
                use_salutation=1 if use_sal else 0
            )
            self._load_contacts()

    def _delete_contact(self):
        row = self.contact_table.currentRow()
        if row < 0:
            return
        cid = int(self.contact_table.item(row, 0).text())
        name = self.contact_table.item(row, 1).text()
        if QMessageBox.question(self, "确认删除", f"确定删除联系人【{name}】吗？") == QMessageBox.Yes:
            self.db.delete_contact(cid)
            self._load_contacts()

    # =========================================================================
    # Tab 2: 全文主语/句式改写规则词典
    # =========================================================================

    def _setup_rewrites_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        self.rewrite_table = QTableWidget(0, 7)
        self.rewrite_table.setHorizontalHeaderLabels([
            "ID", "原短语 (Source)", "改写目标 (Target)", "来源类型", "命中频次", "状态", "过滤条件"
        ])
        self.rewrite_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.rewrite_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.rewrite_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.rewrite_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.rewrite_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.rewrite_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.rewrite_table)

        btn_bar = QHBoxLayout()
        btn_add = QPushButton("➕ 添加手工规则")
        btn_add.clicked.connect(self._add_rewrite_rule)
        btn_toggle = QPushButton("⏯️ 启用/停用")
        btn_toggle.clicked.connect(self._toggle_rewrite_rule)
        btn_del = QPushButton("🗑️ 删除规则")
        btn_del.clicked.connect(self._delete_rewrite_rule)

        btn_bar.addWidget(btn_add)
        btn_bar.addWidget(btn_toggle)
        btn_bar.addWidget(btn_del)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

    def _load_rewrites(self):
        self.rewrite_table.setRowCount(0)
        rules = self.db.get_all_rewrite_rules()
        for r in rules:
            row = self.rewrite_table.rowCount()
            self.rewrite_table.insertRow(row)
            self.rewrite_table.setItem(row, 0, QTableWidgetItem(str(r.get("id"))))
            self.rewrite_table.setItem(row, 1, QTableWidgetItem(r.get("source_pattern", "")))
            self.rewrite_table.setItem(row, 2, QTableWidgetItem(r.get("target_template", "")))

            source_type = "🤖 Diff 自学习" if r.get("learned_from_diff", 0) == 1 else "手工预设"
            self.rewrite_table.setItem(row, 3, QTableWidgetItem(source_type))
            self.rewrite_table.setItem(row, 4, QTableWidgetItem(str(r.get("hit_count", 1))))

            status = "✓ 启用" if r.get("is_enabled", 1) == 1 else "✗ 停用"
            self.rewrite_table.setItem(row, 5, QTableWidgetItem(status))

            filters = []
            if r.get("sender_filter"):
                filters.append(f"发件人={r['sender_filter']}")
            if r.get("target_filter"):
                filters.append(f"收件人={r['target_filter']}")
            self.rewrite_table.setItem(row, 6, QTableWidgetItem("; ".join(filters) or "全局生效"))

    def _add_rewrite_rule(self):
        src, ok1 = QInputDialog.getText(self, "添加改写规则", "原邮件中出现的短语/句式 (例如 '我这边'):")
        if not ok1 or not src.strip():
            return
        tgt, ok2 = QInputDialog.getText(self, "添加改写规则", "改写后的短语 (支持占位符 {sender_name}, 例如 '{sender_name}那边'):")
        if not ok2 or not tgt.strip():
            return

        self.db.add_rewrite_rule(
            source_pattern=src.strip(),
            target_template=tgt.strip(),
            learned_from_diff=0,
            hit_count=5,
            is_enabled=1
        )
        self._load_rewrites()

    def _toggle_rewrite_rule(self):
        row = self.rewrite_table.currentRow()
        if row < 0:
            return
        rid = int(self.rewrite_table.item(row, 0).text())
        curr_status = self.rewrite_table.item(row, 5).text()
        new_enabled = 0 if "启用" in curr_status else 1
        self.db.update_rewrite_rule(rid, is_enabled=new_enabled)
        self._load_rewrites()

    def _delete_rewrite_rule(self):
        row = self.rewrite_table.currentRow()
        if row < 0:
            return
        rid = int(self.rewrite_table.item(row, 0).text())
        src = self.rewrite_table.item(row, 1).text()
        if QMessageBox.question(self, "确认删除", f"确定删除改写规则【{src}】吗？") == QMessageBox.Yes:
            self.db.delete_rewrite_rule(rid)
            self._load_rewrites()

    # =========================================================================
    # Tab 3: 关键词自动流转规则
    # =========================================================================

    def _setup_rules_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        self.rules_table = QTableWidget(0, 8)
        self.rules_table.setHorizontalHeaderLabels([
            "ID", "规则名称", "匹配范围", "关键词列表", "排除词", "默认流转收件人", "默认流转模式", "优先级"
        ])
        self.rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.rules_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.rules_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.rules_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.rules_table)

        btn_bar = QHBoxLayout()
        btn_add = QPushButton("➕ 添加流转规则")
        btn_add.clicked.connect(self._add_match_rule)
        btn_del = QPushButton("🗑️ 删除规则")
        btn_del.clicked.connect(self._delete_match_rule)

        btn_bar.addWidget(btn_add)
        btn_bar.addWidget(btn_del)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

    def _load_match_rules(self):
        self.rules_table.setRowCount(0)
        rules = self.db.get_all_match_rules()
        for r in rules:
            row = self.rules_table.rowCount()
            self.rules_table.insertRow(row)
            self.rules_table.setItem(row, 0, QTableWidgetItem(str(r.get("id"))))
            self.rules_table.setItem(row, 1, QTableWidgetItem(r.get("rule_name", "")))

            scope_map = {"both": "主题与全文", "subject": "仅主题", "body": "仅正文"}
            self.rules_table.setItem(row, 2, QTableWidgetItem(scope_map.get(r.get("match_scope", "both"), "全文")))
            self.rules_table.setItem(row, 3, QTableWidgetItem(r.get("keywords", "")))
            self.rules_table.setItem(row, 4, QTableWidgetItem(r.get("exclude_keywords", "")))

            tgts = ", ".join(r.get("target_emails", []))
            self.rules_table.setItem(row, 5, QTableWidgetItem(tgts))

            mode_map = {"rewrite_new": "改写新建", "standard_forward": "标准转发"}
            self.rules_table.setItem(row, 6, QTableWidgetItem(mode_map.get(r.get("default_send_mode", "rewrite_new"), "改写新建")))
            self.rules_table.setItem(row, 7, QTableWidgetItem(str(r.get("priority", 10))))

    def _add_match_rule(self):
        name, ok1 = QInputDialog.getText(self, "添加流转规则", "规则名称 (例如 '技术协调'):")
        if not ok1 or not name.strip():
            return
        keywords, ok2 = QInputDialog.getText(self, "添加流转规则", "命中关键词 (多个用英文逗号分隔):")
        if not ok2 or not keywords.strip():
            return
        target, ok3 = QInputDialog.getText(self, "添加流转规则", "推荐流转收件人邮箱 (多个用英文逗号分隔):")
        if not ok3 or not target.strip():
            return

        target_list = [t.strip() for t in target.split(",") if t.strip()]
        self.db.add_match_rule(
            rule_name=name.strip(),
            keywords=keywords.strip(),
            target_emails_json=target_list,
            match_scope="both",
            default_send_mode="rewrite_new"
        )
        self._load_match_rules()

    def _delete_match_rule(self):
        row = self.rules_table.currentRow()
        if row < 0:
            return
        rid = int(self.rules_table.item(row, 0).text())
        name = self.rules_table.item(row, 1).text()
        if QMessageBox.question(self, "确认删除", f"确定删除流转规则【{name}】吗？") == QMessageBox.Yes:
            self.db.delete_match_rule(rid)
            self._load_match_rules()

    def _load_all_tabs(self):
        self._load_contacts()
        self._load_rewrites()
        self._load_match_rules()
