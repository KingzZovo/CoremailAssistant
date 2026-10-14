"""Unit tests for RuleEngine."""

import unittest
from coremail_processor.rules.rule_engine import RuleEngine, ProcessingRule, RuleCondition, RuleAction
from coremail_processor.parser.mail_parser import ParsedEmail


class TestRuleEngine(unittest.TestCase):
    def test_rule_matching_subject_contains(self):
        engine = RuleEngine()
        engine.rules = [
            ProcessingRule(
                name="发票规则",
                conditions=[
                    RuleCondition(field="subject", operator="contains", value="发票")
                ],
                actions=[RuleAction(type="mark_read")]
            )
        ]

        email1 = ParsedEmail(msg_id="1", subject="这是一封关于发票的邮件")
        email2 = ParsedEmail(msg_id="2", subject="周例会提醒")

        matches1 = engine.match(email1)
        matches2 = engine.match(email2)

        self.assertEqual(len(matches1), 1)
        self.assertEqual(matches1[0].name, "发票规则")
        self.assertEqual(len(matches2), 0)

    def test_rule_matching_all_conditions(self):
        engine = RuleEngine()
        engine.rules = [
            ProcessingRule(
                name="特定发件人日报",
                match_mode="all",
                conditions=[
                    RuleCondition(field="sender_email", operator="equals", value="boss@company.com"),
                    RuleCondition(field="subject", operator="contains", value="日报"),
                ],
                actions=[RuleAction(type="mark_read")]
            )
        ]

        email1 = ParsedEmail(msg_id="1", sender_email="boss@company.com", subject="今日日报")
        email2 = ParsedEmail(msg_id="2", sender_email="colleague@company.com", subject="今日日报")

        self.assertEqual(len(engine.match(email1)), 1)
        self.assertEqual(len(engine.match(email2)), 0)


if __name__ == "__main__":
    unittest.main()
