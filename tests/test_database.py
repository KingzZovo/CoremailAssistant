"""Unit tests for DatabaseManager and config."""

import os
import tempfile
import unittest
from core.database import DatabaseManager


class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_assistant.db")
        # Reset singleton instance for testing
        DatabaseManager._instance = None
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        DatabaseManager._instance = None
        self.tmp_dir.cleanup()

    def test_init_and_default_settings(self):
        imap_host = self.db.get_setting("imap_host")
        self.assertEqual(imap_host, "mail.example.com")
        self.db.set_setting("imap_host", "mail.testcorp.com")
        self.assertEqual(self.db.get_setting("imap_host"), "mail.testcorp.com")

    def test_contacts_crud_and_habits(self):
        c_id = self.db.add_contact(
            name="张工",
            email="zhang@example.com",
            department="技术部",
            preferred_salutation="张工，你好：",
            use_salutation=1,
            preferred_mode="rewrite_new"
        )
        self.assertGreater(c_id, 0)

        c = self.db.get_contact_by_email("zhang@example.com")
        self.assertIsNotNone(c)
        self.assertEqual(c["name"], "张工")
        self.assertEqual(c["use_salutation"], 1)

        # 模拟学习更新习惯：不加称呼
        self.db.update_contact_habit("zhang@example.com", use_salutation=0)
        c2 = self.db.get_contact_by_email("zhang@example.com")
        self.assertEqual(c2["use_salutation"], 0)

    def test_fulltext_rewrite_rules_and_diff_upsert(self):
        # 初始默认规则应该已写入
        rules = self.db.get_all_rewrite_rules()
        self.assertGreater(len(rules), 0)

        # 模拟从 Diff 学习新增规则
        rule_id, is_new = self.db.upsert_learned_rewrite_rule(
            sender_filter="",
            target_filter="",
            source_pattern="我部门已经核准",
            target_template="{sender_name}部门已经核准"
        )
        self.assertTrue(is_new)
        self.assertGreater(rule_id, 0)

        # 再次学习相同的规则，应累加 hit_count
        rule_id_2, is_new_2 = self.db.upsert_learned_rewrite_rule(
            sender_filter="",
            target_filter="",
            source_pattern="我部门已经核准",
            target_template="{sender_name}部门已经核准"
        )
        self.assertFalse(is_new_2)
        self.assertEqual(rule_id, rule_id_2)

    def test_memos_and_due_reminders(self):
        m_id = self.db.create_memo(
            title="审核周报",
            content_html="<p>请核实本周进度</p>",
            category="重点跟进",
            priority="高",
            remind_at="2026-10-14 12:00"
        )
        self.assertGreater(m_id, 0)

        due = self.db.get_due_memos(now_str="2026-10-14 12:05")
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["title"], "审核周报")

        self.db.mark_memo_reminded(m_id)
        due_after = self.db.get_due_memos(now_str="2026-10-14 12:05")
        self.assertEqual(len(due_after), 0)


if __name__ == "__main__":
    unittest.main()
