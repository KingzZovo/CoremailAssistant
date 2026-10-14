"""Unit tests for MailParser."""

import unittest
from coremail_processor.parser.mail_parser import MailParser, ParsedEmail


class TestMailParser(unittest.TestCase):
    def test_decode_str_ascii(self):
        self.assertEqual(MailParser.decode_str("Hello World"), "Hello World")

    def test_decode_str_utf8(self):
        # =?utf-8?B?5rWL6K+V6YKu5Lu2?= -> "测试邮件"
        encoded = "=?utf-8?B?5rWL6K+V6YKu5Lu2?="
        self.assertEqual(MailParser.decode_str(encoded), "测试邮件")

    def test_decode_str_gbk(self):
        # "发票通知" in GBK base64 is "t6LGsc2o1qo="
        encoded = "=?GBK?B?t6LGsc2o1qo=?="
        self.assertEqual(MailParser.decode_str(encoded), "发票通知")

    def test_parse_simple_email(self):
        raw_email = (
            b"From: =?utf-8?B?5byg5LiJ?= <zhangsan@example.com>\r\n"
            b"To: receiver@example.com\r\n"
            b"Subject: =?utf-8?B?MjAyNuW5tOW6pui0ouWKoeWRqOaKpeWPkeelqA==?=\r\n"
            b"Date: Wed, 14 Oct 2026 10:00:00 +0800\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"\xe8\xbf\x99\xe6\x98\xaf\xe6\xad\xa3\xe6\x96\x87\xe5\x86\x85\xe5\xae\xb9\r\n"
        )

        parsed = MailParser.parse_bytes(raw_email, uid=101)
        self.assertEqual(parsed.uid, 101)
        self.assertIn("zhangsan@example.com", parsed.sender_email)
        self.assertIn("张三", parsed.sender_name)
        self.assertIn("2026年度财务周报发票", parsed.subject)
        self.assertIn("这是正文内容", parsed.body_text)


if __name__ == "__main__":
    unittest.main()
