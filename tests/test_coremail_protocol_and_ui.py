"""Tests for Coremail protocol mode, host/port normalization, DNS/port probe, and UI text cleanups."""

import unittest
from unittest.mock import patch, MagicMock
import socket
from PySide6.QtWidgets import QApplication

from core.mail_client import (
    normalize_host_and_port,
    probe_coremail_server_ports,
    CoremailClient,
    decode_imap_utf7,
    is_system_non_inbox_folder,
)
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

    @patch("socket.gethostbyname")
    @patch("socket.create_connection")
    def test_probe_coremail_all_ports_closed_returns_false(self, mock_connect, mock_gethost):
        mock_gethost.return_value = "192.168.1.100"
        mock_connect.side_effect = socket.timeout("timed out")

        res = probe_coremail_server_ports("192.168.1.100")
        self.assertFalse(res["ok"])
        self.assertIn("超时", res["msg"])
        self.assertNotIn("探测成功", res.get("msg", ""))

    @patch("socket.gethostbyname")
    @patch("socket.create_connection")
    @patch("requests.Session.get")
    def test_probe_coremail_firewall_only_http_open(self, mock_http_get, mock_connect, mock_gethost):
        mock_gethost.return_value = "10.10.1.5"
        def side_effect(address, timeout=1.5):
            ip, port = address
            if port == 80:
                return MagicMock()
            raise socket.timeout("timed out")
        mock_connect.side_effect = side_effect
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_http_get.return_value = mock_resp

        res = probe_coremail_server_ports("10.10.1.5")
        self.assertTrue(res["ok"])
        self.assertEqual(res["http_base_url"], "http://10.10.1.5")
        self.assertIsNone(res["imap_port"])
        self.assertIsNone(res["smtp_port"])
        self.assertIn("HTTP/Coremail WebAPI", res["msg"])

    @patch("requests.Session.post")
    def test_coremail_client_webapi_login(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "code": "S_OK",
            "var": {"sid": "sid_test_123456"}
        }
        mock_post.return_value = mock_resp

        cfg = {
            "protocol_mode": "coremail",
            "coremail_server": "http://mail.intranet.corp:8080",
            "email_account": "tester@intranet.corp",
            "email_password": "mypassword",
        }
        client = CoremailClient(cfg)
        base_url, sid = client._http_login()
        self.assertEqual(sid, "sid_test_123456")
        self.assertEqual(base_url, "http://mail.intranet.corp:8080")

    @patch("requests.Session.post")
    @patch("requests.Session.get")
    def test_coremail_client_webapi_fetch_new_emails_eml(self, mock_get, mock_post):
        def post_side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "func=user:login" in url:
                resp.json.return_value = {"code": "S_OK", "var": {"sid": "sid_xyz"}}
            elif "func=mbox:listMessages" in url:
                resp.json.return_value = {
                    "code": "S_OK",
                    "var": [{"id": "mid_1001"}]
                }
            return resp
        mock_post.side_effect = post_side_effect

        eml_bytes = (
            b"From: =?utf-8?B?5byg5LiJ?= <zhangsan@corp.cn>\r\n"
            b"To: <tester@corp.cn>\r\n"
            b"Subject: =?utf-8?B?5rWL6K+V6YKu5Lu2?=\r\n"
            b"Date: Mon, 19 Oct 2026 10:00:00 +0800\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
            b"Hello via Coremail WebAPI EML!\r\n"
        )
        mock_eml_resp = MagicMock()
        mock_eml_resp.status_code = 200
        mock_eml_resp.content = eml_bytes
        mock_get.return_value = mock_eml_resp

        cfg = {
            "protocol_mode": "coremail",
            "coremail_server": "http://10.0.0.8",
            "email_account": "tester@corp.cn",
            "email_password": "pwd",
        }
        client = CoremailClient(cfg, attachment_root="/tmp/test_att")
        emails = client.fetch_new_emails(existing_uids=set(), max_fetch=10)
        self.assertEqual(len(emails), 1)
        self.assertEqual(emails[0]["uid"], "mid_1001")
        self.assertEqual(emails[0]["subject"], "测试邮件")
        self.assertEqual(emails[0]["sender_name"], "张三")
        self.assertEqual(emails[0]["sender_email"], "zhangsan@corp.cn")
        self.assertIn("Hello via Coremail WebAPI EML!", emails[0]["body_text"])

    @patch("requests.Session.post")
    def test_coremail_client_webapi_send_email(self, mock_post):
        def post_side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "func=user:login" in url:
                resp.json.return_value = {"code": "S_OK", "var": {"sid": "sid_compose_test"}}
            elif "func=mbox:compose" in url:
                resp.json.return_value = {"code": "S_OK", "var": {"id": "sent_1"}}
            return resp
        mock_post.side_effect = post_side_effect

        cfg = {
            "protocol_mode": "coremail",
            "coremail_server": "http://10.0.0.8",
            "email_account": "tester@corp.cn",
            "email_password": "pwd",
        }
        client = CoremailClient(cfg)
        client.send_email(
            to_addrs=["target@corp.cn"],
            cc_addrs=["cc@corp.cn"],
            subject="自动化通知",
            html_body="<p>内容已送达</p>",
            plain_body="内容已送达",
            attachment_paths=[],
            save_to_sent=True
        )
        self.assertTrue(mock_post.called)
        calls = [c for c in mock_post.call_args_list if "func=mbox:compose" in c[0][0]]
        self.assertEqual(len(calls), 1)
        payload = calls[0][1]["json"]
        self.assertEqual(payload["attrs"]["subject"], "自动化通知")
        self.assertEqual(payload["attrs"]["to"], ["target@corp.cn"])

    @patch("core.mail_client.probe_coremail_server_ports")
    @patch("requests.Session.post")
    def test_coremail_client_test_connection_firewall_webapi(self, mock_post, mock_probe):
        mock_probe.return_value = {
            "ok": True,
            "host": "10.0.0.8",
            "resolved_ip": "10.0.0.8",
            "http_base_url": "http://10.0.0.8:8080",
            "imap_port": None,
            "imap_ssl": False,
            "smtp_port": None,
            "smtp_ssl": False,
            "open_channels": ["HTTP/Coremail WebAPI (http://10.0.0.8:8080)"],
            "msg": "探测成功"
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": "S_OK", "var": {"sid": "sid_conn_123"}}
        mock_post.return_value = mock_resp

        cfg = {
            "protocol_mode": "coremail",
            "coremail_server": "http://10.0.0.8:8080",
            "email_account": "tester@corp.cn",
            "email_password": "pwd",
        }
        client = CoremailClient(cfg)
        res = client.test_connection()
        self.assertTrue(res["ok"])
        self.assertIn("WebAPI", res["msg"])

    def test_decode_imap_utf7(self):
        # ASCII folder name
        self.assertEqual(decode_imap_utf7("INBOX"), "INBOX")
        self.assertEqual(decode_imap_utf7("MyProject"), "MyProject")
        # Escaped &
        self.assertEqual(decode_imap_utf7("Research &- Development"), "Research & Development")
        # Chinese folders (Modified UTF-7)
        decoded = decode_imap_utf7("&V4NXPpCuTvY-")
        self.assertTrue(len(decoded) > 0)
        self.assertFalse(decoded.startswith("&"))

    def test_is_system_non_inbox_folder(self):
        # Should be filtered (True):
        self.assertTrue(is_system_non_inbox_folder(2, "草稿箱"))
        self.assertTrue(is_system_non_inbox_folder(3, "已发送"))
        self.assertTrue(is_system_non_inbox_folder(4, "已删除"))
        self.assertTrue(is_system_non_inbox_folder(5, "垃圾邮件"))
        self.assertTrue(is_system_non_inbox_folder(99, "Sent Messages"))
        self.assertTrue(is_system_non_inbox_folder(99, "Drafts"))
        self.assertTrue(is_system_non_inbox_folder(99, "Trash"))
        self.assertTrue(is_system_non_inbox_folder(99, "Spam"))
        self.assertTrue(is_system_non_inbox_folder(99, "Junk"))

        # Should NOT be filtered (False):
        self.assertFalse(is_system_non_inbox_folder(1, "收件箱"))
        self.assertFalse(is_system_non_inbox_folder("1", "INBOX"))
        self.assertFalse(is_system_non_inbox_folder(10, "项目协同组"))
        self.assertFalse(is_system_non_inbox_folder(11, "研发周报"))

    @patch("requests.Session.post")
    def test_multi_folder_headers_and_lazy_load(self, mock_post):
        def post_side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "func=user:login" in url:
                resp.json.return_value = {"code": "S_OK", "var": {"sid": "sid_multifolder"}}
            elif "func=mbox:getAllFolders" in url:
                resp.json.return_value = {
                    "code": "S_OK",
                    "var": [
                        {"id": 1, "name": "收件箱"},
                        {"id": 2, "name": "草稿箱"},
                        {"id": 3, "name": "已发送"},
                        {"id": 10, "name": "重要项目组"},
                    ]
                }
            elif "func=mbox:listMessages" in url:
                req_json = kwargs.get("json", {})
                fid = req_json.get("fid")
                if fid == 1:
                    # Test dictionary variant: var={"messages": [...]}
                    resp.json.return_value = {
                        "code": "S_OK",
                        "var": {
                            "messages": [
                                {
                                    "id": "mid_inbox_1",
                                    "subject": "收件箱邮件",
                                    "from": "alice@corp.cn",
                                    "to": ["bob@corp.cn"],
                                    "receivedDate": 1700000000,
                                    "summary": "来自收件箱的摘要"
                                }
                            ]
                        }
                    }
                elif fid == 10:
                    # Test list variant: var=[...]
                    resp.json.return_value = {
                        "code": "S_OK",
                        "var": [
                            {
                                "id": "mid_proj_2",
                                "subject": "紧急协调邮件",
                                "from": "leader@corp.cn",
                                "to": ["bob@corp.cn"],
                                "receivedDate": 1700001000,
                                "summary": "请尽快流转"
                            }
                        ]
                    }
                else:
                    resp.json.return_value = {"code": "S_OK", "var": []}
            return resp

        mock_post.side_effect = post_side_effect

        cfg = {
            "protocol_mode": "coremail",
            "coremail_server": "http://10.0.0.8",
            "email_account": "tester@corp.cn",
            "email_password": "pwd",
        }
        client = CoremailClient(cfg)
        headers, folder_count = client.fetch_new_email_headers(existing_uids=set(), max_fetch_per_folder=5)
        self.assertEqual(folder_count, 2)
        self.assertEqual(len(headers), 2)
        uids = [h["uid"] for h in headers]
        self.assertIn("mid_inbox_1", uids)
        self.assertIn("mid_proj_2", uids)

        inbox_em = [h for h in headers if h["uid"] == "mid_inbox_1"][0]
        proj_em = [h for h in headers if h["uid"] == "mid_proj_2"][0]
        self.assertEqual(inbox_em["folder_name"], "收件箱")
        self.assertEqual(inbox_em["is_body_loaded"], 0)
        self.assertEqual(proj_em["folder_name"], "重要项目组")
        self.assertEqual(proj_em["is_body_loaded"], 0)

    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_fetch_single_email_detail(self, mock_post, mock_get):
        login_resp = MagicMock()
        login_resp.status_code = 200
        login_resp.json.return_value = {"code": "S_OK", "var": {"sid": "sid_detail_test"}}
        mock_post.return_value = login_resp

        eml_bytes = (
            b"From: =?utf-8?B?5byg5LiJ?= <zhangsan@corp.cn>\r\n"
            b"To: <tester@corp.cn>\r\n"
            b"Subject: =?utf-8?B?5byA5Lya6YCa55+l?=\r\n"
            b"Date: Mon, 19 Oct 2026 10:00:00 +0800\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
            + "下午两点准时开会。\r\n".encode("utf-8")
        )
        mock_eml_resp = MagicMock()
        mock_eml_resp.status_code = 200
        mock_eml_resp.content = eml_bytes
        mock_get.return_value = mock_eml_resp

        cfg = {
            "protocol_mode": "coremail",
            "coremail_server": "http://10.0.0.8",
            "email_account": "tester@corp.cn",
            "email_password": "pwd",
        }
        client = CoremailClient(cfg, attachment_root="/tmp/test_single_att")
        detail = client.fetch_single_email_detail("mid_test_detail", folder_name="重要项目组")
        self.assertEqual(detail["is_body_loaded"], 1)
        self.assertIn("下午两点准时开会", detail["body_text"])


if __name__ == "__main__":
    unittest.main()
