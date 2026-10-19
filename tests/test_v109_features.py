"""Unit tests for CoremailAssistant v1.0.9 features:
1. Rejection of Coremail polluted web shell HTML
2. parse_email_date_to_timestamp robust parsing across formats
3. Database timestamp sorting (newest to oldest) and folder counts & filtering
4. mark_email_need_action and mark_email_no_action bi-directional flow
5. Enhanced ML feature extraction and habit matrix learning (pair, sender, folder)
6. MainWindow UI folder filter, context menu, and bi-directional marking actions
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.database import DatabaseManager, parse_email_date_to_timestamp
from core.mail_client import _is_polluted_coremail_shell, _clean_and_extract_html_and_text
from core.ml_learner import LocalEmailLearner


class TestV109Features(unittest.TestCase):
    """v1.0.9 核心功能测试套件"""

    def setUp(self):
        DatabaseManager._instance = None

    def tearDown(self):
        DatabaseManager._instance = None

    def test_polluted_coremail_shell_rejection(self):
        """测试对 Coremail 网盘下载 Web 外壳的精准识别与拦截"""
        shell_1 = "<!DOCTYPE html><html><head><title>网盘文件下载</title></head><body>下载中...</body></html>"
        shell_2 = "<div>/coremail/bundle/polyfill.js?v=eb2b3919</div>"
        shell_3 = "<script>var $, _ X = window.Coremail;</script>"
        shell_4 = '<link rel="stylesheet" id="jSkin" href="/coremail/bundle/X.a3565-1.css">'

        self.assertTrue(_is_polluted_coremail_shell(shell_1))
        self.assertTrue(_is_polluted_coremail_shell(shell_2))
        self.assertTrue(_is_polluted_coremail_shell(shell_3))
        self.assertTrue(_is_polluted_coremail_shell(shell_4))

        # 真实合法邮件正文绝不能误杀
        normal_email_html = "<div><p>王经理好，这是本周的项目进展汇报，请查收。</p></div>"
        self.assertFalse(_is_polluted_coremail_shell(normal_email_html))

    def test_parse_email_date_to_timestamp(self):
        """测试全格式日期解析为秒级时间戳及标准化 YYYY-MM-DD HH:MM"""
        # 1. 13 位毫秒时间戳 (int & str)
        ts1, s1 = parse_email_date_to_timestamp(1792390000000)
        self.assertEqual(ts1, 1792390000)
        self.assertTrue(s1.startswith("2026-") or len(s1) == 16)

        ts2, s2 = parse_email_date_to_timestamp("1792390000000")
        self.assertEqual(ts2, 1792390000)

        # 2. 10 位秒级时间戳
        ts3, s3 = parse_email_date_to_timestamp(1792390000)
        self.assertEqual(ts3, 1792390000)

        # 3. ISO 日期字符串
        ts4, s4 = parse_email_date_to_timestamp("2026-10-19 14:30:00")
        self.assertGreater(ts4, 0)
        self.assertEqual(s4, "2026-10-19 14:30")

        # 4. RFC2822 邮件头格式
        ts5, s5 = parse_email_date_to_timestamp("Mon, 19 Oct 2026 10:30:00 +0800")
        self.assertGreater(ts5, 0)
        self.assertTrue(s5.startswith("2026-10-19"))

    def test_database_timestamp_sorting_and_folder_filtering(self):
        """测试邮件列表严格按 received_timestamp DESC 排序及文件夹筛选"""
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            DatabaseManager._instance = None
            db = DatabaseManager(tmp.name)

            # 插入三封不同时间、不同文件夹的邮件
            db.insert_email({
                "uid": "mail_old",
                "subject": "较早的收件箱邮件",
                "folder_name": "收件箱",
                "date_str": "2026-10-18 10:00:00",
                "received_timestamp": 1792300000,
                "is_matched": 1,
                "status": "pending"
            })
            db.insert_email({
                "uid": "mail_new",
                "subject": "最新的自定义文件夹邮件",
                "folder_name": "重点项目",
                "date_str": "2026-10-19 12:00:00",
                "received_timestamp": 1792393200,
                "is_matched": 0,
                "status": "ignored"
            })
            db.insert_email({
                "uid": "mail_mid",
                "subject": "中期的收件箱邮件",
                "folder_name": "收件箱",
                "date_str": "2026-10-19 08:00:00",
                "received_timestamp": 1792378800,
                "is_matched": 1,
                "status": "pending"
            })

            # 1. 验证排序：必须从最新到最旧排列
            all_emails = db.get_all_emails()
            self.assertEqual(len(all_emails), 3)
            self.assertEqual(all_emails[0]["uid"], "mail_new")
            self.assertEqual(all_emails[1]["uid"], "mail_mid")
            self.assertEqual(all_emails[2]["uid"], "mail_old")

            # 2. 验证文件夹统计
            counts = db.get_folder_counts()
            count_map = {c["folder_name"]: c["count"] for c in counts}
            self.assertEqual(count_map.get("收件箱"), 2)
            self.assertEqual(count_map.get("重点项目"), 1)

            # 3. 验证文件夹筛选
            inbox_emails = db.get_all_emails(folder_filter="收件箱")
            self.assertEqual(len(inbox_emails), 2)
            self.assertEqual([e["uid"] for e in inbox_emails], ["mail_mid", "mail_old"])

            proj_emails = db.get_all_emails(folder_filter="重点项目")
            self.assertEqual(len(proj_emails), 1)
            self.assertEqual(proj_emails[0]["uid"], "mail_new")

    def test_database_bidirectional_flow_marking(self):
        """测试 mark_email_need_action 与 mark_email_no_action 双向状态切换"""
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            DatabaseManager._instance = None
            db = DatabaseManager(tmp.name)

            db.insert_email({
                "uid": "test_flow_1",
                "subject": "待流转测试邮件",
                "folder_name": "收件箱",
                "is_matched": 0,
                "status": "pending"
            })

            # 标记为待流转
            db.mark_email_need_action("test_flow_1")
            em1 = db.get_email_by_uid("test_flow_1")
            self.assertEqual(em1["is_matched"], 1)
            self.assertEqual(em1["status"], "pending")

            # 标记为无需流转
            db.mark_email_no_action("test_flow_1")
            em2 = db.get_email_by_uid("test_flow_1")
            self.assertEqual(em2["is_matched"], 0)
            self.assertEqual(em2["status"], "ignored")

    def test_ml_learner_habit_matrices_and_features(self):
        """测试机器学习多维特征（文件夹、发件人、收件人关系、附件）与习惯矩阵记忆"""
        with tempfile.NamedTemporaryFile(suffix=".pkl") as tmp_m:
            learner = LocalEmailLearner(model_path=tmp_m.name)

            email_data = {
                "uid": "ml_test_101",
                "sender_email": "boss@corp.cn",
                "to_list": [{"email": "me@corp.cn"}],
                "cc_list": [],
                "folder_name": "领导邮件",
                "subject": "请速落实下季度规划",
                "body_text": "规划方案请于本周五前发给业务部张工。",
                "attachments": [{"filename": "plan.docx"}]
            }

            # 验证特征文本中包含强特征 Token
            feat_text = learner._build_full_feature_text(
                sender_email=email_data["sender_email"],
                cc_list=email_data["cc_list"],
                subject=email_data["subject"],
                full_body=email_data["body_text"],
                folder_name=email_data["folder_name"],
                to_list=email_data["to_list"],
                attachments=email_data["attachments"],
                my_email="me@corp.cn"
            )
            self.assertIn("__folder_领导邮件__", feat_text)
            self.assertIn("__from_boss@corp.cn__", feat_text)
            self.assertIn("__me_in_to__", feat_text)
            self.assertIn("__has_attach__", feat_text)

            # 训练用户习惯：对来自 boss@corp.cn 发给 zhang@corp.cn 的邮件，习惯使用 rewrite_new
            learner.learn_from_user_action(
                email_data=email_data,
                action_label=1,
                chosen_mode="rewrite_new",
                chosen_f_emails=["zhang@corp.cn"],
                my_email="me@corp.cn"
            )

            pair_key = "boss@corp.cn::zhang@corp.cn"
            self.assertIn(pair_key, learner.pair_mode_stats)
            self.assertEqual(learner.pair_mode_stats[pair_key]["rewrite_new"], 1)
            self.assertEqual(learner.sender_mode_stats["boss@corp.cn"]["rewrite_new"], 1)
            self.assertEqual(learner.folder_mode_stats["领导邮件"]["rewrite_new"], 1)

            # 预测：习惯模式优先返回 rewrite_new，且收件人推荐 zhang@corp.cn
            contacts = [{"name": "张工", "email": "zhang@corp.cn"}]
            pred = learner.predict_email(email_data, candidate_contacts=contacts, my_email="me@corp.cn")
            self.assertEqual(pred["recommended_mode"], "rewrite_new")
            self.assertIn("zhang@corp.cn", pred["predicted_f_emails"])

    def test_main_window_v109_folder_and_flow_buttons(self):
        """测试 MainWindow 文件夹筛选组件与双向标记按钮交互"""
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            DatabaseManager._instance = None
            db = DatabaseManager(tmp.name)

            # 插入两封邮件：一封待流转，一封普通邮件
            db.insert_email({
                "uid": "ui_email_pending",
                "subject": "需要流转的公文",
                "sender_name": "办公室",
                "sender_email": "office@corp.cn",
                "folder_name": "行政通知",
                "date_str": "2026-10-19 14:00:00",
                "received_timestamp": 1792394000,
                "is_matched": 1,
                "status": "pending",
                "body_text": "请各部门速传阅"
            })
            db.insert_email({
                "uid": "ui_email_normal",
                "subject": "普通日常邮件",
                "sender_name": "技术支持",
                "sender_email": "support@corp.cn",
                "folder_name": "技术讨论",
                "date_str": "2026-10-19 13:00:00",
                "received_timestamp": 1792390400,
                "is_matched": 0,
                "status": "ignored",
                "body_text": "今天服务器正常维护"
            })

            window = MainWindow()

            # 1. 验证文件夹下拉框与 AI 重扫按钮存在
            self.assertTrue(hasattr(window, "folder_filter"))
            self.assertTrue(hasattr(window, "btn_rescan_ml"))
            self.assertTrue(hasattr(window, "btn_mark_pending"))
            self.assertTrue(hasattr(window, "btn_ignore"))

            # 2. 刷新文件夹选项
            window._update_folder_filter_options()
            self.assertGreaterEqual(window.folder_filter.count(), 2)

            # 3. 待流转视图下只显示待流转邮件
            window.current_view = "pending"
            window._refresh_current_view()
            self.assertEqual(window.item_list.count(), 1)
            item0 = window.item_list.item(0)
            self.assertIn("[📁 行政通知]", item0.text())

            # 选中待流转邮件：显示“🚫 无需流转”，隐藏“📌 标记为待流转”
            data_pending = item0.data(Qt.UserRole)
            window._display_email_detail(data_pending)
            self.assertFalse(window.btn_ignore.isHidden())
            self.assertTrue(window.btn_mark_pending.isHidden())

            # 4. 全部邮件视图下
            window.current_view = "all_emails"
            window._refresh_current_view()
            self.assertEqual(window.item_list.count(), 2)

            # 选中普通邮件：显示“📌 标记为待流转”，隐藏“🚫 无需流转”
            normal_item = None
            for i in range(window.item_list.count()):
                it = window.item_list.item(i)
                d = it.data(Qt.UserRole)
                if d["uid"] == "ui_email_normal":
                    normal_item = it
                    break
            self.assertIsNotNone(normal_item)
            window._display_email_detail(normal_item.data(Qt.UserRole))
            self.assertFalse(window.btn_mark_pending.isHidden())
            self.assertTrue(window.btn_ignore.isHidden())

            # 5. 测试点击“标记为待流转”
            window.selected_email = normal_item.data(Qt.UserRole)
            window._mark_current_email_as_pending()
            updated_normal = window.db.get_email_by_uid("ui_email_normal")
            self.assertEqual(updated_normal["is_matched"], 1)
            self.assertEqual(updated_normal["status"], "pending")

            # 6. 测试备忘录视图下隐藏文件夹筛选与 AI 重扫按钮
            window.current_view = "memos"
            window._refresh_current_view()
            self.assertTrue(window.folder_filter.isHidden())
            self.assertTrue(window.btn_rescan_ml.isHidden())

            window.close()


if __name__ == "__main__":
    unittest.main()
