"""Settings Dialog for CoremailAssistant.
Configures IMAP/SMTP server connection, credentials, polling intervals,
Machine Learning status & model reset, and local Ollama parameters.
"""

from typing import Dict, Any, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QSpinBox, QComboBox, QGroupBox,
    QMessageBox, QScrollArea, QWidget
)

from core.database import DatabaseManager
from core.mail_client import CoremailClient, probe_coremail_server_ports
from core.ml_learner import LocalEmailLearner
from core.ollama_client import OllamaClient


class SettingsDialog(QDialog):
    """系统与邮箱配置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.db = DatabaseManager()
        self.learner = LocalEmailLearner()

        self.setWindowTitle("系统设置 - CoremailAssistant")
        self.resize(750, 680)
        self.http_base_url = ""
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 1. 邮箱服务器与账号凭证
        mail_group = QGroupBox("论客邮箱 (Coremail) 协议与服务器设置")
        mail_layout = QVBoxLayout(mail_group)

        # 协议类型选择
        proto_row = QHBoxLayout()
        proto_row.addWidget(QLabel("协议类型："))
        self.protocol_mode = QComboBox()
        self.protocol_mode.addItem("Coremail 专用协议（同论客客户端，仅需填一个服务器地址）", "coremail")
        self.protocol_mode.addItem("IMAP / SMTP 标准协议（手动分别指定端口）", "imap_smtp")
        self.protocol_mode.currentIndexChanged.connect(self._on_protocol_mode_changed)
        proto_row.addWidget(self.protocol_mode, 1)
        mail_layout.addLayout(proto_row)

        # Coremail 专用协议：单服务器地址输入与自动探测区域
        self.coremail_box = QWidget()
        coremail_layout = QVBoxLayout(self.coremail_box)
        coremail_layout.setContentsMargins(0, 4, 0, 4)
        c_row = QHBoxLayout()
        c_row.addWidget(QLabel("服务器地址："))
        self.coremail_server = QLineEdit()
        self.coremail_server.setPlaceholderText("例如 192.168.1.50 或 mail.company.com（与论客客户端一致）")
        c_row.addWidget(self.coremail_server, 2)
        self.btn_detect_server = QPushButton("🔍 自动检测端口与连接")
        self.btn_detect_server.clicked.connect(self._detect_coremail_ports)
        c_row.addWidget(self.btn_detect_server)
        coremail_layout.addLayout(c_row)

        self.coremail_tip_lbl = QLabel("💡 提示：与论客客户端一致，可直接粘贴客户端【设置->帐号管理】里的服务器 IP 或域名。点击“自动检测”将自动探测内网端口并测试连接。")
        self.coremail_tip_lbl.setStyleSheet("color: #64748B; font-size: 11px;")
        coremail_layout.addWidget(self.coremail_tip_lbl)
        mail_layout.addWidget(self.coremail_box)

        # IMAP/SMTP 标准协议：手动输入区域
        self.manual_server_box = QWidget()
        manual_layout = QVBoxLayout(self.manual_server_box)
        manual_layout.setContentsMargins(0, 4, 0, 4)

        # IMAP
        imap_row = QHBoxLayout()
        imap_row.addWidget(QLabel("IMAP 主机："))
        self.imap_host = QLineEdit()
        self.imap_host.setPlaceholderText("例如 mail.company.com 或 IP")
        imap_row.addWidget(self.imap_host, 2)
        imap_row.addWidget(QLabel("端口："))
        self.imap_port = QSpinBox()
        self.imap_port.setRange(1, 65535)
        self.imap_port.setValue(993)
        imap_row.addWidget(self.imap_port)
        self.imap_ssl = QCheckBox("SSL 加密")
        self.imap_ssl.setChecked(True)
        imap_row.addWidget(self.imap_ssl)
        manual_layout.addLayout(imap_row)

        # SMTP
        smtp_row = QHBoxLayout()
        smtp_row.addWidget(QLabel("SMTP 主机："))
        self.smtp_host = QLineEdit()
        self.smtp_host.setPlaceholderText("例如 mail.company.com 或 IP")
        smtp_row.addWidget(self.smtp_host, 2)
        smtp_row.addWidget(QLabel("端口："))
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(465)
        smtp_row.addWidget(self.smtp_port)
        self.smtp_ssl = QCheckBox("SSL 加密")
        self.smtp_ssl.setChecked(True)
        smtp_row.addWidget(self.smtp_ssl)
        manual_layout.addLayout(smtp_row)

        mail_layout.addWidget(self.manual_server_box)

        # 账号凭据
        acc_row = QHBoxLayout()
        acc_row.addWidget(QLabel("邮箱账号："))
        self.email_account = QLineEdit()
        self.email_account.setPlaceholderText("your_name@company.com")
        acc_row.addWidget(self.email_account, 2)
        acc_row.addWidget(QLabel("密码/授权码："))
        self.email_password = QLineEdit()
        self.email_password.setEchoMode(QLineEdit.Password)
        self.email_password.setPlaceholderText("论客邮箱登录密码或客户端专用码")
        acc_row.addWidget(self.email_password, 2)
        mail_layout.addLayout(acc_row)

        disp_row = QHBoxLayout()
        disp_row.addWidget(QLabel("发件人显示姓名："))
        self.sender_display_name = QLineEdit()
        self.sender_display_name.setPlaceholderText("例如 张三 (发信时在收件方显示的中文名)")
        disp_row.addWidget(self.sender_display_name, 1)

        btn_test = QPushButton("🔌 测试连接")
        btn_test.clicked.connect(self._test_connection)
        disp_row.addWidget(btn_test)
        mail_layout.addLayout(disp_row)

        layout.addWidget(mail_group)

        # 2. 自动化轮询与智能化模式
        auto_group = QGroupBox("自动化收信与处理模式")
        auto_layout = QVBoxLayout(auto_group)

        poll_row = QHBoxLayout()
        poll_row.addWidget(QLabel("后台自动收信轮询间隔："))
        self.poll_interval = QSpinBox()
        self.poll_interval.setRange(15, 3600)
        self.poll_interval.setValue(60)
        self.poll_interval.setSuffix(" 秒")
        poll_row.addWidget(self.poll_interval)

        poll_row.addWidget(QLabel("流转初筛模式："))
        self.filter_mode = QComboBox()
        self.filter_mode.addItem("规则优先 + 本地机器学习兜底 (推荐)", "rules_and_ml")
        self.filter_mode.addItem("纯本地全文机器学习 (无须写规则)", "ml_only")
        self.filter_mode.addItem("仅关键词匹配规则", "rules_only")
        self.filter_mode.addItem("本地初筛 + Ollama 大模型深度润色", "ollama_hybrid")
        poll_row.addWidget(self.filter_mode, 1)
        auto_layout.addLayout(poll_row)

        behav_row = QHBoxLayout()
        self.chk_auto_read = QCheckBox("邮件流转成功后自动标记为已读")
        behav_row.addWidget(self.chk_auto_read)
        self.chk_cc_sender = QCheckBox("默认勾选抄送原发件人")
        behav_row.addWidget(self.chk_cc_sender)
        behav_row.addStretch()
        auto_layout.addLayout(behav_row)

        layout.addWidget(auto_group)

        # 3. 本地机器学习引擎状态面板
        ml_group = QGroupBox("🤖 全文增量机器学习引擎状态面板")
        ml_layout = QVBoxLayout(ml_group)

        self.ml_status_lbl = QLabel()
        self.ml_status_lbl.setStyleSheet("color: #475569; line-height: 1.6;")
        self._refresh_ml_status()
        ml_layout.addWidget(self.ml_status_lbl)

        ml_btn_box = QHBoxLayout()
        btn_refresh_ml = QPushButton("🔄 刷新状态")
        btn_refresh_ml.clicked.connect(self._refresh_ml_status)
        btn_reset_ml = QPushButton("🗑️ 重置/清空本地模型")
        btn_reset_ml.setObjectName("btn_danger")
        btn_reset_ml.setProperty("danger", True)
        btn_reset_ml.clicked.connect(self._reset_ml_models)

        ml_btn_box.addWidget(btn_refresh_ml)
        ml_btn_box.addWidget(btn_reset_ml)
        ml_btn_box.addStretch()
        ml_layout.addLayout(ml_btn_box)

        layout.addWidget(ml_group)

        # 4. 本地大模型 (Ollama) 配置
        ollama_group = QGroupBox("🦙 本地大模型 (Ollama) 深度扩展")
        ollama_layout = QVBoxLayout(ollama_group)

        self.chk_ollama = QCheckBox("启用本地 Ollama 进行复杂语义摘要与主语深度润色")
        ollama_layout.addWidget(self.chk_ollama)

        ol_row = QHBoxLayout()
        ol_row.addWidget(QLabel("服务地址："))
        self.ollama_url = QLineEdit("http://127.0.0.1:11434")
        ol_row.addWidget(self.ollama_url, 1)

        ol_row.addWidget(QLabel("模型名称："))
        self.ollama_model = QLineEdit("qwen2.5:3b")
        ol_row.addWidget(self.ollama_model, 1)

        btn_detect_ol = QPushButton("🔍 检测 Ollama 服务")
        btn_detect_ol.clicked.connect(self._detect_ollama)
        ol_row.addWidget(btn_detect_ol)
        ollama_layout.addLayout(ol_row)

        layout.addWidget(ollama_group)

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll, 1)

        # 5. 底部保存与取消按钮
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(btn_cancel)

        btn_save = QPushButton("💾 保存配置")
        btn_save.setObjectName("btn_primary")
        btn_save.setProperty("primary", True)
        btn_save.clicked.connect(self._save_settings)
        bottom_bar.addWidget(btn_save)

        main_layout.addLayout(bottom_bar)

    def _on_protocol_mode_changed(self):
        mode = self.protocol_mode.currentData()
        if mode == "coremail":
            self.coremail_box.setVisible(True)
            self.manual_server_box.setVisible(False)
        else:
            self.coremail_box.setVisible(False)
            self.manual_server_box.setVisible(True)

    def _detect_coremail_ports(self):
        server = self.coremail_server.text().strip()
        if not server:
            QMessageBox.warning(self, "提示", "请先输入论客服务器地址（IP 或域名）")
            return

        res = probe_coremail_server_ports(server)
        if not res.get("ok"):
            QMessageBox.critical(self, "检测失败", res.get("msg", "无法连接到该服务器"))
            return

        clean_host = res.get("host", server)
        imap_p = res.get("imap_port")
        imap_s = res.get("imap_ssl", False)
        smtp_p = res.get("smtp_port")
        smtp_s = res.get("smtp_ssl", False)
        http_base = res.get("http_base_url")

        if http_base:
            self.http_base_url = http_base

        if imap_p is not None:
            self.imap_host.setText(clean_host)
            self.imap_port.setValue(imap_p)
            self.imap_ssl.setChecked(imap_s)

        if smtp_p is not None:
            self.smtp_host.setText(clean_host)
            self.smtp_port.setValue(smtp_p)
            self.smtp_ssl.setChecked(smtp_s)

        channel_lines = []
        if http_base:
            channel_lines.append(f"• Coremail WebAPI 专用通道: {http_base} (HTTP/HTTPS)")
        if imap_p is not None:
            channel_lines.append(f"• IMAP 收信端口: {imap_p} (SSL 加密: {'开启' if imap_s else '关闭'})")
        if smtp_p is not None:
            channel_lines.append(f"• SMTP 发信端口: {smtp_p} (SSL 加密: {'开启' if smtp_s else '关闭'})")
        if res.get("pop3_port") is not None:
            channel_lines.append(f"• POP3 收信端口: {res.get('pop3_port')}")

        channel_text = "\n".join(channel_lines)
        extra_note = ""
        if http_base and imap_p is None:
            extra_note = (
                "\n\n💡 提示：检测到内网服务器未开放标准 IMAP/SMTP 端口（通常被防火墙拦截），"
                "但开放了 HTTP/HTTPS Web 服务。系统已自动开启与官方论客客户端相同的 WebAPI 专用协议进行收发！"
            )

        msg = (
            f"🎉 论客服务器端口检测成功！\n\n"
            f"• 服务器主机: {clean_host}\n"
            f"• 解析 IP: {res.get('resolved_ip')}\n"
            f"• 开放服务与端口：\n{channel_text}{extra_note}\n\n"
            f"您可以点击下方的“🔌 测试连接”验证邮箱账号密码。"
        )
        QMessageBox.information(self, "检测成功", msg)

    def _refresh_ml_status(self):
        sample_count = self.db.get_sample_count()
        diff_count = self.db.get_learned_diff_rules_count()
        is_fitted = "已启动增量训练" if self.learner.action_fitted else "待积累训练样本"

        self.ml_status_lbl.setText(
            f"• <b>模型运行状态：</b>{is_fitted}<br>"
            f"• <b>已学习历史邮件全文样本数：</b>{sample_count} 封<br>"
            f"• <b>从全文编辑 Diff 中自动学习到的改写短语：</b>{diff_count} 条<br>"
            f"• <b>硬件开销评估：</b>纯 CPU 在线轻量级提取，内存占用 &lt;60MB，预测延迟 &lt;10ms"
        )

    def _reset_ml_models(self):
        if QMessageBox.question(
            self, "确认重置",
            "确定要重置本地机器学习模型吗？这将清空当前学习到的预测权重（数据库历史样本与规则不会删除）。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) == QMessageBox.Yes:
            self.learner.reset_models()
            self._refresh_ml_status()
            QMessageBox.information(self, "重置完成", "本地机器学习模型已重置为初始状态")

    def _test_connection(self):
        proto_mode = self.protocol_mode.currentData()
        c_srv = self.coremail_server.text().strip()

        if proto_mode == "coremail" and not c_srv:
            QMessageBox.warning(self, "提示", "请填写论客服务器地址")
            return

        cfg = {
            "protocol_mode": proto_mode,
            "coremail_server": c_srv,
            "http_base_url": getattr(self, "http_base_url", ""),
            "imap_host": self.imap_host.text().strip(),
            "imap_port": self.imap_port.value(),
            "imap_ssl": self.imap_ssl.isChecked(),
            "smtp_host": self.smtp_host.text().strip(),
            "smtp_port": self.smtp_port.value(),
            "smtp_ssl": self.smtp_ssl.isChecked(),
            "email_account": self.email_account.text().strip(),
            "email_password": self.email_password.text(),
        }
        client = CoremailClient(cfg)
        res = client.test_connection()
        if res.get("ok"):
            if client.imap_port:
                self.imap_port.setValue(client.imap_port)
                self.imap_ssl.setChecked(client.imap_ssl)
            if client.smtp_port:
                self.smtp_port.setValue(client.smtp_port)
                self.smtp_ssl.setChecked(client.smtp_ssl)
            if getattr(client, "_cached_base_url", None):
                self.http_base_url = client._cached_base_url
            QMessageBox.information(self, "连接成功", res.get("msg"))
        else:
            QMessageBox.critical(self, "连接失败", res.get("msg"))

    def _detect_ollama(self):
        client = OllamaClient(
            base_url=self.ollama_url.text().strip(),
            default_model=self.ollama_model.text().strip()
        )
        if client.is_available():
            models = client.list_local_models()
            models_str = ", ".join(models) if models else "服务正常（暂未检测到已下载模型）"
            QMessageBox.information(self, "检测成功", f"Ollama 服务运行正常！\n本地可用模型: {models_str}")
        else:
            QMessageBox.warning(self, "检测提示", "无法连接到 Ollama 服务，请确认后台是否已启动 ollama")

    def _load_settings(self):
        st = self.db.get_all_settings()

        self.http_base_url = st.get("http_base_url", "")
        proto_mode = st.get("protocol_mode", "coremail")
        idx_p = self.protocol_mode.findData(proto_mode)
        if idx_p >= 0:
            self.protocol_mode.setCurrentIndex(idx_p)
        self.coremail_server.setText(st.get("coremail_server", ""))
        self._on_protocol_mode_changed()

        self.imap_host.setText(st.get("imap_host", ""))
        self.imap_port.setValue(int(st.get("imap_port", 993) or 993))
        self.imap_ssl.setChecked(st.get("imap_ssl", "1") == "1")

        self.smtp_host.setText(st.get("smtp_host", ""))
        self.smtp_port.setValue(int(st.get("smtp_port", 465) or 465))
        self.smtp_ssl.setChecked(st.get("smtp_ssl", "1") == "1")

        self.email_account.setText(st.get("email_account", ""))
        self.email_password.setText(st.get("email_password", ""))
        self.sender_display_name.setText(st.get("sender_display_name", ""))

        self.poll_interval.setValue(int(st.get("poll_interval", 60) or 60))
        self.chk_auto_read.setChecked(st.get("auto_mark_read", "0") == "1")
        self.chk_cc_sender.setChecked(st.get("default_include_sender_in_cc", "1") == "1")

        mode = st.get("filter_mode", "rules_and_ml")
        idx = self.filter_mode.findData(mode)
        if idx >= 0:
            self.filter_mode.setCurrentIndex(idx)

        self.chk_ollama.setChecked(st.get("ollama_enabled", "0") == "1")
        self.ollama_url.setText(st.get("ollama_url", "http://127.0.0.1:11434"))
        self.ollama_model.setText(st.get("ollama_model", "qwen2.5:3b"))

    def _save_settings(self):
        proto_mode = self.protocol_mode.currentData()
        c_srv = self.coremail_server.text().strip()

        imap_h = self.imap_host.text().strip()
        smtp_h = self.smtp_host.text().strip()
        if proto_mode == "coremail" and c_srv:
            if not imap_h:
                imap_h = c_srv
            if not smtp_h:
                smtp_h = c_srv

        data = {
            "protocol_mode": proto_mode,
            "coremail_server": c_srv,
            "http_base_url": getattr(self, "http_base_url", ""),
            "imap_host": imap_h,
            "imap_port": str(self.imap_port.value()),
            "imap_ssl": "1" if self.imap_ssl.isChecked() else "0",
            "smtp_host": smtp_h,
            "smtp_port": str(self.smtp_port.value()),
            "smtp_ssl": "1" if self.smtp_ssl.isChecked() else "0",
            "email_account": self.email_account.text().strip(),
            "email_password": self.email_password.text(),
            "sender_display_name": self.sender_display_name.text().strip(),
            "poll_interval": str(self.poll_interval.value()),
            "auto_mark_read": "1" if self.chk_auto_read.isChecked() else "0",
            "default_include_sender_in_cc": "1" if self.chk_cc_sender.isChecked() else "0",
            "filter_mode": self.filter_mode.currentData(),
            "ollama_enabled": "1" if self.chk_ollama.isChecked() else "0",
            "ollama_url": self.ollama_url.text().strip(),
            "ollama_model": self.ollama_model.text().strip(),
        }
        self.db.update_settings(data)
        QMessageBox.information(self, "保存成功", "系统配置已成功保存！")
        self.accept()
