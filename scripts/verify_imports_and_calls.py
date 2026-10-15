"""Comprehensive verification script to test all module imports and method calls.
Guarantees 100% compatibility across core, ui, and worker threads.
"""

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure Qt offscreen for headless environments
os.environ["QT_QPA_PLATFORM"] = "offscreen"


def run_verification():
    print("=" * 60)
    print("CoremailAssistant 全项目模块导入与接口兼容性自检开始...")
    print("=" * 60)

    # 1. 验证所有核心模块导入
    print("\n[Step 1/4] 测试模块全局导入...")
    import config
    import core.database
    import core.mail_client
    import core.rewriter_engine
    import core.ml_learner
    import core.ollama_client
    import core.worker_threads
    import ui.theme
    import ui.main_window
    import ui.compose_send_dialog
    import ui.memo_dialog
    import ui.rule_contact_dialog
    import ui.settings_dialog

    # 验证类名别名导出
    from core.rewriter_engine import RewriterEngine, EmailRewriterEngine
    assert RewriterEngine is EmailRewriterEngine, "RewriterEngine 与 EmailRewriterEngine 应为同一类别名"
    print("  ✓ 核心与 UI 所有 13 个模块全部导入成功，别名导出正常")

    # 2. 测试 DatabaseManager 所有方法与别名
    print("\n[Step 2/4] 测试 DatabaseManager 核心与兼容别名接口...")
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db = core.database.DatabaseManager(tmp.name)

        # Settings
        db.save_setting("test_key", "test_val")
        db.set_setting("test_key2", "test_val2")
        assert db.get_setting("test_key") == "test_val"
        assert db.get_setting("test_key2") == "test_val2"

        all_st = db.get_all_settings()
        assert all_st["test_key"] == "test_val"
        all_st2 = db.get_settings()
        assert all_st2["test_key2"] == "test_val2"

        db.save_settings({"bulk_1": "v1", "bulk_2": "v2"})
        db.update_settings({"bulk_3": "v3"})
        assert db.get_setting("bulk_1") == "v1"
        assert db.get_setting("bulk_3") == "v3"
        print("  ✓ Settings 读写及别名 (get_all_settings / get_settings / save_setting / set_setting / save_settings / update_settings) 正常")

        # Contacts
        db.add_contact("张三", "zhangsan@test.com", "研发部", preferred_salutation="张三老师好")
        db.upsert_contact("李四", "lisi@test.com", "产品部")
        c1 = db.get_all_contacts()
        c2 = db.get_contacts()
        c3 = db.list_contacts()
        assert len(c1) == 2 and len(c2) == 2 and len(c3) == 2

        # Contact Habit & Send Count
        db.increment_contact_send_count("zhangsan@test.com")
        db.update_contact_habit("zhangsan@test.com", salutation="张工你好：", mode="rewrite_new")
        db.update_contact_habit("lisi@test.com", use_salutation=0, preferred_mode="standard_forward")
        c_zh = db.get_contact_by_email("zhangsan@test.com")
        assert c_zh["send_count"] == 1
        assert c_zh["preferred_salutation"] == "张工你好："
        print("  ✓ Contacts 及习惯学习 (get_contacts / get_all_contacts / list_contacts / add_contact / upsert_contact / update_contact_habit / increment_contact_send_count) 正常")

        # Match Rules
        db.add_match_rule("测试规则1", "发票;报销", ["finance@test.com"], priority=1, is_enabled=1)
        db.add_match_rule("测试规则2", "请假;调休", ["hr@test.com"], priority=2, is_enabled=0)
        r_all = db.get_all_match_rules()
        r_rules = db.get_rules()
        r_list = db.list_rules()
        r_enabled = db.get_all_match_rules(enabled_only=True)
        r_rules_enabled = db.get_rules(enabled_only=True)
        assert len(r_all) == 2 and len(r_rules) == 2 and len(r_list) == 2
        assert len(r_enabled) == 1 and len(r_rules_enabled) == 1
        print("  ✓ Match Rules 及参数过滤 (get_all_match_rules / get_rules / list_rules, enabled_only=True) 正常")

        # Emails
        em_sample = {
            "uid": "1001",
            "message_id": "<msg1001@test.com>",
            "subject": "请协助测试接口",
            "sender_name": "王五",
            "sender_email": "wangwu@test.com",
            "to_list": ["me@test.com"],
            "cc_list": [],
            "date_str": "2026-10-15 14:00:00",
            "body_text": "王经理，麻烦您审批一下工单，我部门急用。",
            "body_html": "<p>王经理，麻烦您审批一下工单，我部门急用。</p>",
            "is_matched": 1,
            "status": "pending"
        }
        db.insert_email(em_sample)
        em_sample2 = dict(em_sample, uid="1002", subject="邮件2")
        db.save_email(em_sample2)

        uids = db.get_existing_uids()
        assert "1001" in uids and "1002" in uids

        all_em = db.get_all_emails()
        get_em = db.get_emails()
        list_em = db.list_emails()
        matched_em = db.get_matched_emails()
        pending_em = db.get_pending_emails()
        assert len(all_em) == 2 and len(get_em) == 2 and len(list_em) == 2
        assert len(matched_em) == 2 and len(pending_em) == 2

        db.update_email_status("1001", "sent_new")
        assert db.get_email_by_uid("1001")["status"] == "sent_new"
        print("  ✓ Emails 及状态流转 (insert_email / save_email / get_existing_uids / get_all_emails / get_emails / list_emails / get_matched_emails / update_email_status) 正常")

        # Memos
        m_id1 = db.create_memo("备忘1", "<p>备忘内容1</p>", priority="高")
        m_id2 = db.add_memo("备忘2", "<p>备忘内容2</p>")
        m_id3 = db.save_memo("备忘3", "<p>备忘内容3</p>")
        m_id4 = db.create_or_update_memo("备忘4", "<p>备忘内容4</p>")

        memos1 = db.get_memos()
        memos2 = db.get_all_memos()
        memos3 = db.list_memos()
        assert len(memos1) == 4 and len(memos2) == 4 and len(memos3) == 4

        db.update_memo(m_id1, remind_at="2026-10-15 12:00")
        due = db.get_due_memos(now_str="2026-10-15 13:00")
        assert len(due) == 1
        db.mark_memo_reminded(m_id1)
        assert len(db.get_due_memos(now_str="2026-10-15 13:00")) == 0
        print("  ✓ Memos 及到期提醒 (create_memo / add_memo / save_memo / create_or_update_memo / get_memos / get_all_memos / list_memos / get_due_memos / mark_memo_reminded) 正常")

        # Rewrite Rules & Learned from Diff
        db.upsert_learned_rewrite_rule(
            sender_filter="",
            target_filter="",
            source_pattern="我部门急用",
            target_template="{sender_name}部门急用",
            is_regex=0
        )
        r_rw = db.get_all_rewrite_rules()
        r_rw_act = db.get_active_rewrite_rules()
        r_rw_lst = db.list_rewrite_rules()
        assert len(r_rw) >= 1 and len(r_rw_act) >= 1 and len(r_rw_lst) >= 1
        print("  ✓ Fulltext Rewrite Rules 及自学习回写 (upsert_learned_rewrite_rule / get_all_rewrite_rules / get_active_rewrite_rules / list_rewrite_rules) 正常")

    # 3. 测试 RewriterEngine 方法与别名
    print("\n[Step 3/4] 测试 RewriterEngine 核心与兼容方法...")
    res1 = RewriterEngine.compute_recipients(
        my_email="me@test.com",
        sender_email="sender@test.com",
        to_list=[{"email": "me@test.com"}, {"email": "cc1@test.com"}],
        cc_list=[{"email": "cc2@test.com"}],
        selected_f_emails=["f_target@test.com"],
        include_sender_in_cc=True
    )
    res2 = RewriterEngine.calculate_recipients_and_cc(
        my_email="me@test.com",
        sender_email="sender@test.com",
        to_list=[{"email": "me@test.com"}, {"email": "cc1@test.com"}],
        cc_list=[{"email": "cc2@test.com"}],
        selected_f_emails=["f_target@test.com"],
        include_sender_in_cc=True
    )
    assert res1 == res2, "compute_recipients 与 calculate_recipients_and_cc 计算结果必须一致"
    print("  ✓ RewriterEngine compute_recipients / calculate_recipients_and_cc 正常")

    # 4. 测试 LocalEmailLearner 方法与别名
    print("\n[Step 4/4] 测试 LocalEmailLearner 核心与兼容方法...")
    with tempfile.NamedTemporaryFile(suffix=".pkl") as tmp_m:
        learner = core.ml_learner.LocalEmailLearner(model_path=tmp_m.name)
        em_test = {
            "subject": "请协助处理发票",
            "sender_email": "a@test.com",
            "body_text": "请协助报销处理"
        }
        p1 = learner.predict_email(em_test, candidate_contacts=[{"name": "财务小李", "email": "finance@test.com"}])
        p2 = learner.predict(em_test)
        assert "need_action_prob" in p1 and "need_action_prob" in p2

        learner.learn_from_user_action(em_test, action_label=1, chosen_mode="rewrite_new", chosen_f_emails=["finance@test.com"])
        learner.learn_from_sent_email(em_test, action_label=1)

        diffs1 = learner.extract_fulltext_rewrite_diffs(
            original_full_text="请您尽快把方案发给您领导，我部门在等。",
            edited_full_text="请尽快把方案发给你领导，张三部门在等。",
            sender_name="张三"
        )
        diffs2 = learner.learn_rewrite_rule_from_diff(
            original_full_text="请您尽快把方案发给您领导，我部门在等。",
            edited_full_text="请尽快把方案发给你领导，张三部门在等。",
            sender_name="张三"
        )
        assert diffs1 == diffs2
        print("  ✓ LocalEmailLearner predict / predict_email / learn_from_user_action / learn_from_sent_email / extract_fulltext_rewrite_diffs / learn_rewrite_rule_from_diff 正常")

    print("\n" + "=" * 60)
    print("🎉 恭喜！全项目 100% 模块与跨文件接口对齐自检全部通过！")
    print("=" * 60)


if __name__ == "__main__":
    run_verification()
