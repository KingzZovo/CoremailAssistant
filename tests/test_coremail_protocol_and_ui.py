"""Tests for Coremail protocol mode, host/port normalization, DNS/port probe, and UI text cleanups."""

import unittest
from unittest.mock import patch, MagicMock
import socket
from PySide6.QtWidgets import QApplication

from core.mail_client import normalize_host_and_port, probe_coremail_server_ports, CoremailClient
from ui.settings_dialog import SettingsDialog
from ui.main_window import MainWindow
from ui.compose_send_dialog import ComposeAndSendDialog


class TestCoremailProtocolAndUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_normalize_host_and_port(self):
        # 1. URL with http, port, and path
        host, port = normalize_host_and_port("http://192.168.1.50:8080/coremail/", 993)
        self.assertEqual(host, "192.168.1.50")
        self.assertEqual(port, 8080)

        # 2. URL with https and domain
        host, port = normalize_host_and_port("https://mail.company.com/webmail", 465)
        self.assertEqual(host, "mail.company.com")
        self.assertEqual(port, 465)

        # 3. Host:port
        host, port = normalize_host_and_port("10.0.0.1:143", 993)
        self.assertEqual(host, "10.0.0.1")
        self.assertEqual(port, 143)

        # 4. Pure IP or domain with spaces
        host, port = normalize_host_and_port("  192.168.10.25  ", 993)
        self.assertEqual(host, "192.168.10.25")
        self.assertEqual(port, 993)

        # 5. Empty host
        host, port = normalize_host_and_port("", 993)
        self.assertEqual(host, "")
        self.assertEqual(port, 993)

    @patch("socket.gethostbyname")
    @patch("socket.create_connection")
    def test_probe_coremail_server_ports(self, mock_connect, mock_gethost):
        mock_gethost.return_value = "192.168.1.50"
        
        # Scenario: Only 143 and 25 open (intranet non-SSL Coremail)
        def side_effect(address, timeout=2.0):
            ip, port = address
            if port in (143, 25):
                return MagicMock()
            raise ConnectionRefusedError()
        mock_connect.side_effect = side_effect

        res = probe_coremail_server_ports("http://192.168.1.50:8080/coremail")
        self.assertTrue(res["ok"])
        self.assertEqual(res["host"], "192.168.1.50")
        self.assertEqual(res["resolved_ip"], "192.168.1.50")
        self.assertEqual(res["imap_port"], 143)
        self.assertFalse(res["imap_ssl"])
        self.assertEqual(res["smtp_port"], 25)
        self.assertFalse(res["smtp_ssl"])

    @patch("socket.gethostbyname")
    def test_probe_coremail_dns_failure(self, mock_gethost):
        err = socket.gaierror(11001, "getaddrinfo failed")
        mock_gethost.side_effect = err

        res = probe_coremail_server_ports("invalid-domain-xxxx")
        self.assertFalse(res["ok"])
        self.assertIn("11001", res["msg"])
        self.assertIn("内网 IP 地址", res["msg"])

    def test_coremail_client_init_single_address_mode(self):
        cfg = {
            "protocol_mode": "coremail",
            "coremail_server": "http://192.168.10.88:8080/coremail",
            "imap_port": 143,
            "imap_ssl": False,
            "smtp_port": 25,
            "smtp_ssl": False,
            "email_account": "user@test.corp",
            "email_password": "secret",
        }
        client = CoremailClient(cfg)
        self.assertEqual(client.imap_host, "192.168.10.88")
        self.assertEqual(client.smtp_host, "192.168.10.88")
        self.assertEqual(client.protocol_mode, "coremail")

    def test_ui_labels_and_buttons_clean_of_placeholder_letters(self):
        # 1. Main Window
        win = MainWindow()
        self.assertEqual(win.btn_rewrite_new.text(), "✨ 改写为新邮件发送")
        self.assertEqual(win.btn_forward.text(), "↪️ 标准带引文转发")

        # Test dynamic update when selecting an email with suggested contact
        test_email = {
            "id": 9999,
            "uid": "test-9999",
            "subject": "项目进度同步",
            "sender_name": "王工",
            "sender_email": "wang@corp.cn",
            "to_list": [{"name": "我", "email": "me@corp.cn"}],
            "cc_list": [],
            "date_str": "2026-10-15 10:00",
            "suggested_to": ["zhang@corp.cn"],
            "recommended_mode": "rewrite_new",
            "body_text": "请查收进度",
        }
        win._display_email_detail(test_email)
        self.assertIn("✨ 改写为新邮件（推荐发给：", win.btn_rewrite_new.text())
        self.assertIn("推荐收件人：", win.detail_header_lbl.text())
        self.assertNotIn("推荐收件人 (F)：", win.detail_header_lbl.text())

        # 2. Compose Send Dialog
        dlg = ComposeAndSendDialog(test_email, parent=win)
        self.assertEqual(dlg.btn_mode_rewrite.text(), "✨ 改写为新邮件（脱壳改称呼与主语）")
        self.assertEqual(dlg.btn_mode_forward.text(), "↪️ 标准带引文转发")
        self.assertIn("抄送原发件人（王工）", dlg.chk_include_sender.text())
        self.assertNotIn("抄送原发件人 A", dlg.chk_include_sender.text())

        # 3. Settings Dialog
        s_dlg = SettingsDialog(parent=win)
        self.assertEqual(s_dlg.chk_cc_sender.text(), "默认勾选抄送原发件人")
        self.assertNotIn("原发件人 A", s_dlg.chk_cc_sender.text())
        self.assertEqual(s_dlg.protocol_mode.count(), 2)

        # Toggle protocol mode
        s_dlg.protocol_mode.setCurrentIndex(0)  # Coremail
        self.assertFalse(s_dlg.coremail_box.isHidden())
        self.assertTrue(s_dlg.manual_server_box.isHidden())

        s_dlg.protocol_mode.setCurrentIndex(1)  # IMAP/SMTP
        self.assertTrue(s_dlg.coremail_box.isHidden())
        self.assertFalse(s_dlg.manual_server_box.isHidden())


if __name__ == "__main__":
    unittest.main()
