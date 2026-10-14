"""Comprehensive end-to-end integration test for CoremailAssistant."""

import os
import tempfile
import unittest

from config import DEFAULT_SETTINGS
from core.database import DatabaseManager
from core.rewriter_engine import RewriterEngine
from core.ml_learner import LocalEmailLearner


class TestCoremailAssistantIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_assistant.db")
        self.model_path = os.path.join(self.tmp_dir.name, "test_models.pkl")

        DatabaseManager._instance = None
        self.db = DatabaseManager(self.db_path)
        self.learner = LocalEmailLearner(self.model_path)

    def tearDown(self):
        DatabaseManager._instance = None
        self.tmp_dir.cleanup()

    def test_full_workflow_rewrite_diff_and_habits(self):
        # 1. 录入常用联系人
        c_id = self.db.add_contact(
            name="张三丰",
            email="zhangsf@example.com",
            department="运维部",
            preferred_salutation="张工，你好：",
            use_salutation=1
        )
        self.assertGreater(c_id, 0)

        # 2. 模拟拉取到一封新邮件入库
        raw_email = {
            "uid": "99901",
            "message_id": "<99901@mail.example.com>",
            "subject": "申请开通核心数据库访问权限",
            "sender_name": "王工",
            "sender_email": "wangg@example.com",
            "to_list": [{"name": "我", "email": "me@example.com"}],
            "cc_list": [{"name": "主管", "email": "manager@example.com"}],
            "date_str": "2026-10-14 10:30:00",
            "body_text": "各位领导，你们好：\n我部门因项目上线需要，特此申请开通只读访问权限。请您审批。",
            "body_html": "<p>各位领导，你们好：</p><p>我部门因项目上线需要，特此申请开通只读访问权限。请您审批。</p>",
            "attachments": [],
            "status": "pending"
        }
        self.db.insert_email(raw_email)

        # 3. 机器学习初筛预测
        contacts = self.db.get_all_contacts()
        pred = self.learner.predict_email(raw_email, contacts)
        self.assertIn("recommended_mode", pred)
        self.assertIn("need_action_prob", pred)

        # 4. 构建改写发信内容 (rewrite_new 模式)
        composed = RewriterEngine.build_compose_content(
            mode="rewrite_new",
            email_data=raw_email,
            target_contacts=[self.db.get_contact_by_email("zhangsf@example.com")],
            selected_f_emails=["zhangsf@example.com"]
        )

        # 验证称呼与主语改写
        self.assertEqual(composed["salutation"], "张工，你好：")
        self.assertIn("王工部门因项目上线需要", composed["plain_body"])
        self.assertIn("请审批", composed["plain_body"])

        # 5. 计算收件人与抄送人联动
        to_addrs, cc_addrs = RewriterEngine.compute_recipients(
            my_email="me@example.com",
            sender_email="wangg@example.com",
            to_list=raw_email["to_list"],
            cc_list=raw_email["cc_list"],
            selected_f_emails=["zhangsf@example.com"],
            include_sender_in_cc=True
        )
        self.assertEqual(to_addrs, ["zhangsf@example.com"])
        self.assertIn("wangg@example.com", cc_addrs)
        self.assertIn("manager@example.com", cc_addrs)

        # 6. 模拟用户在富文本编辑器中做了进一步改写并发送：
        #    例如将 "请审批" 进一步微调为 "请协助审批"
        final_edited_body = composed["plain_body"].replace("请审批", "请协助审批")

        # 闭环 A: 提取 Diff 规则并存入词典
        diffs = LocalEmailLearner.extract_fulltext_rewrite_diffs(
            original_full_text=raw_email["body_text"],
            edited_full_text=final_edited_body,
            sender_name="王工"
        )
        for src, tgt in diffs:
            self.db.upsert_learned_rewrite_rule("", "", src, tgt)

        # 闭环 B: 在线增量学习
        self.learner.learn_from_user_action(
            email_data=raw_email,
            action_label=1,
            chosen_mode="rewrite_new",
            chosen_f_emails=["zhangsf@example.com"]
        )

        # 闭环 C: 更新联系人发信频次
        self.db.increment_contact_send_count("zhangsf@example.com")
        updated_c = self.db.get_contact_by_email("zhangsf@example.com")
        self.assertEqual(updated_c["send_count"], 1)

        # 闭环 D: 更新邮件状态
        self.db.update_email_status("99901", "sent_new")
        saved_email = self.db.get_email_by_uid("99901")
        self.assertEqual(saved_email["status"], "sent_new")

        # 7. 备忘录联动与到期检测
        m_id = self.db.create_memo(
            title="跟踪核心库权限开通进度",
            content_html="<p>已发邮件给张工，等待配置完毕回复</p>",
            email_uid="99901",
            checklist=[{"text": "确认IP白名单", "done": True}, {"text": "测试连接", "done": False}],
            category="重点跟进",
            priority="高",
            remind_at="2026-10-14 11:00"
        )
        self.assertGreater(m_id, 0)
        due_memos = self.db.get_due_memos(now_str="2026-10-14 11:30")
        self.assertEqual(len(due_memos), 1)
        self.assertEqual(due_memos[0]["title"], "跟踪核心库权限开通进度")


if __name__ == "__main__":
    unittest.main()
