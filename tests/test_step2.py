"""Unit tests for Step 2 modules: mail_client, rewriter_engine, and ml_learner."""

import os
import tempfile
import unittest
from core.rewriter_engine import RewriterEngine
from core.ml_learner import LocalEmailLearner


class TestRewriterEngine(unittest.TestCase):
    def test_strip_original_salutation_with_salutation(self):
        body_with_sal = "张经理，您好：\n这是关于第四季度项目预算的报告，请查收。"
        stripped, removed = RewriterEngine.strip_original_salutation_safely(body_with_sal)
        self.assertIn("张经理", removed)
        self.assertTrue(stripped.startswith("这是关于第四季度项目预算"))

    def test_strip_original_salutation_without_salutation(self):
        # 原邮件直接说明事情，未包含称呼，绝不可误删首句！
        body_no_sal = "关于服务器维护的通知：本周六晚22:00将进行停机维护。"
        stripped, removed = RewriterEngine.strip_original_salutation_safely(body_no_sal)
        self.assertEqual(removed, "")
        self.assertEqual(stripped, body_no_sal)

    def test_apply_fulltext_rewrites(self):
        text = "我这边已经核实完毕，请您审批相关流程。"
        rewritten = RewriterEngine.apply_fulltext_rewrites(
            text=text,
            sender_name="李四",
            sender_email="lisi@example.com"
        )
        self.assertIn("李四那边已经核实完毕", rewritten)
        self.assertIn("请审批相关流程", rewritten)

    def test_rewrite_html_preserving_format(self):
        raw_html = (
            "<div>"
            "<p>王总，你好：</p>"
            "<p>我部门已经完成初审，详情见下表：</p>"
            "<table border='1'><tr><td style='color:red;'><b>待审批金额</b></td><td>10000</td></tr></table>"
            "</div>"
        )
        rewritten_html = RewriterEngine.rewrite_html_preserving_format(
            raw_html=raw_html,
            sender_name="王五",
            sender_email="wangwu@example.com",
            target_email="director@example.com",
            salutation="主任，你好：",
            closing_sign="请协助审批，谢谢！"
        )
        self.assertIn("主任，你好：", rewritten_html)
        self.assertIn("王五部门已经完成初审", rewritten_html)
        self.assertIn("<table", rewritten_html)
        self.assertIn("color:red", rewritten_html)
        self.assertIn("请协助审批，谢谢！", rewritten_html)

    def test_compute_recipients(self):
        to_list = [{"name": "A", "email": "a@example.com"}, {"name": "B", "email": "b@example.com"}]
        cc_list = [{"name": "C", "email": "c@example.com"}]
        my_email = "me@example.com"
        sender_email = "boss@example.com"
        selected_f = ["f@example.com"]

        new_to, new_cc = RewriterEngine.compute_recipients(
            my_email=my_email,
            sender_email=sender_email,
            to_list=to_list,
            cc_list=cc_list,
            selected_f_emails=selected_f,
            include_sender_in_cc=True
        )

        self.assertEqual(new_to, ["f@example.com"])
        self.assertIn("boss@example.com", new_cc)
        self.assertIn("a@example.com", new_cc)
        self.assertIn("b@example.com", new_cc)
        self.assertIn("c@example.com", new_cc)
        self.assertNotIn("me@example.com", new_cc)
        self.assertNotIn("f@example.com", new_cc)


class TestLocalEmailLearner(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.model_path = os.path.join(self.tmp_dir.name, "test_models.pkl")
        self.learner = LocalEmailLearner(self.model_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_learning_and_prediction(self):
        email_data = {
            "sender_email": "dev@company.com",
            "subject": "周度数据汇总",
            "body_text": "本周系统运行平稳，请核对附件中的数据表。",
            "cc_list": []
        }
        candidates = [
            {"name": "小王", "email": "wang@company.com"},
            {"name": "小李", "email": "li@company.com"}
        ]

        # 初始预测
        pred_before = self.learner.predict_email(email_data, candidates)
        self.assertIn("need_action_prob", pred_before)

        # 模拟用户流转并选择小王
        self.learner.learn_from_user_action(
            email_data=email_data,
            action_label=1,
            chosen_mode="rewrite_new",
            chosen_f_emails=["wang@company.com"]
        )

        # 再次预测，wang@company.com 应该得分排在最前
        pred_after = self.learner.predict_email(email_data, candidates)
        self.assertTrue(pred_after["need_action_prob"] >= 0.5)
        self.assertIn("wang@company.com", pred_after["predicted_f_emails"])

    def test_diff_extraction(self):
        orig_text = "张总，你好。我部申请开通内网访问权限。请您审批。"
        edited_text = "王总，你好。研发部申请开通内网访问权限。请协助审批。"
        sender_name = "张三"

        diffs = LocalEmailLearner.extract_fulltext_rewrite_diffs(
            original_full_text=orig_text,
            edited_full_text=edited_text,
            sender_name=sender_name
        )
        # 应捕捉到 "我" -> "研发" 以及 "您" -> "协助" 等短语替换
        self.assertTrue(any("我" in src for src, tgt in diffs))
        self.assertTrue(any("您" in src for src, tgt in diffs))


if __name__ == "__main__":
    unittest.main()
