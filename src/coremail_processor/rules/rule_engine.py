"""Rule engine for email matching and filtering."""

from typing import List, Dict, Any, Optional
from pathlib import Path
import re
import yaml
from pydantic import BaseModel, Field
from loguru import logger
from ..parser.mail_parser import ParsedEmail


class RuleCondition(BaseModel):
    field: str  # subject, sender, sender_email, body, has_attachment
    operator: str = "contains"  # contains, equals, startswith, regex, not_contains
    value: Any = None


class RuleAction(BaseModel):
    type: str  # save_attachments, mark_read, move_folder, log
    params: Dict[str, Any] = Field(default_factory=dict)


class ProcessingRule(BaseModel):
    name: str
    enabled: bool = True
    priority: int = 10
    match_mode: str = "all"  # all | any
    conditions: List[RuleCondition] = Field(default_factory=list)
    actions: List[RuleAction] = Field(default_factory=list)


class RuleEngine:
    """邮件规则匹配引擎"""

    def __init__(self, rules_file: Optional[str] = None):
        self.rules: List[ProcessingRule] = []
        if rules_file:
            self.load_rules(rules_file)

    def load_rules(self, rules_file: str):
        path = Path(rules_file)
        if not path.exists():
            logger.warning(f"规则文件未找到: {rules_file}，将不加载自定义规则")
            return

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        raw_rules = data.get("rules", [])
        self.rules = [ProcessingRule(**r) for r in raw_rules if r.get("enabled", True)]
        # 按优先级升序排序
        self.rules.sort(key=lambda x: x.priority)
        logger.info(f"已加载并启用 {len(self.rules)} 条邮件处理规则")

    def evaluate_condition(self, condition: RuleCondition, email: ParsedEmail) -> bool:
        """评估单个条件"""
        field_val = ""
        field_name = condition.field.lower()

        if field_name == "subject":
            field_val = email.subject
        elif field_name in ("sender", "from"):
            field_val = email.sender
        elif field_name == "sender_email":
            field_val = email.sender_email
        elif field_name in ("body", "content"):
            field_val = email.body_text or email.body_html
        elif field_name == "has_attachment":
            has_att = len(email.attachments) > 0
            expected = bool(condition.value)
            return has_att == expected
        else:
            logger.warning(f"未知的条件字段: {condition.field}")
            return False

        op = condition.operator.lower()
        val = str(condition.value) if condition.value is not None else ""

        if op == "contains":
            return val.lower() in field_val.lower()
        elif op == "not_contains":
            return val.lower() not in field_val.lower()
        elif op == "equals":
            return field_val.strip().lower() == val.strip().lower()
        elif op == "startswith":
            return field_val.lower().startswith(val.lower())
        elif op == "regex":
            return bool(re.search(val, field_val, re.IGNORECASE))
        return False

    def match(self, email: ParsedEmail) -> List[ProcessingRule]:
        """返回所有匹配此邮件的规则"""
        matched_rules = []
        for rule in self.rules:
            if not rule.conditions:
                continue

            results = [self.evaluate_condition(c, email) for c in rule.conditions]
            is_match = all(results) if rule.match_mode == "all" else any(results)

            if is_match:
                logger.debug(f"邮件 [{email.subject}] 命中规则: {rule.name}")
                matched_rules.append(rule)

        return matched_rules
