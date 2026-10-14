"""Coremail email rewriting, salutation adaptation, and HTML format preservation engine."""

import re
import html
from bs4 import BeautifulSoup, NavigableString
from typing import Dict, Any, List, Tuple, Optional


# 严格版称呼识别正则：必须包含明确称呼身份词或问候语，且独占首行（绝不误伤无称呼邮件的正文第一句）
STRICT_SALUTATION_REGEX = re.compile(
    r"^\s*(?:"
    r"(?:尊敬的|亲爱的|Dear)\s*[^\n，,：:!！]{1,15}[，,：:!！]"
    r"|"
    r"[^\n，,：:!！]{1,12}(?:先生|女士|老师|教授|经理|主任|处长|科长|局长|总|工|哥|姐|同志|同学|领导|各位|大家)[，,：:\s]*(?:您好|你好|早上好|下午好|晚上好|见信好)?[，,：:!！]"
    r"|"
    r"[^\n，,：:!！]{1,10}[，,：:\s]+(?:您好|你好|早上好|下午好|晚上好)[，,：:!！]"
    r")\s*\n*",
    re.IGNORECASE
)

DEFAULT_FULLTEXT_REWRITES = [
    {"source": "麻烦您", "target": "麻烦你"},
    {"source": "请您协助", "target": "请协助"},
    {"source": "请您帮忙", "target": "请帮忙"},
    {"source": "请您确认", "target": "请确认"},
    {"source": "请您审阅", "target": "请审阅"},
    {"source": "请您审批", "target": "请审批"},
    {"source": "请您查收", "target": "请查收"},
    {"source": "请您知悉", "target": "请知悉"},
    {"source": "发给您", "target": "同步给你"},
    {"source": "向您汇报", "target": "同步一下"},
    {"source": "我这边", "target": "{sender_name}那边"},
    {"source": "我们这边", "target": "{sender_name}团队那边"},
    {"source": "我部门", "target": "{sender_name}部门"},
    {"source": "我科室", "target": "{sender_name}科室"},
    {"source": "我方", "target": "{sender_name}方"},
]


class RewriterEngine:
    """支持无称呼自适应、全文主语/人称替换、以及 HTML 富文本保留改写的双模式引擎"""

    @staticmethod
    def strip_original_salutation_safely(body_text: str) -> Tuple[str, str]:
        """
        安全剥离原邮件开头称呼：
        若发件人 A 根本没写称呼（直接写事情），则原封不动保留全文，绝不误删首句！
        """
        if not body_text:
            return "", ""
        text = body_text.lstrip()
        match = STRICT_SALUTATION_REGEX.match(text)
        if match:
            removed = match.group(0).strip()
            return text[match.end():].lstrip(), removed
        return text, ""

    @staticmethod
    def generate_target_salutation(
        target_contacts: List[Dict[str, Any]],
        fallback_emails: List[str]
    ) -> str:
        """
        生成对收件人 F 的称呼；如果学习到用户对该联系人习惯不加称呼 (use_salutation == 0)，则返回空字符串。
        """
        if target_contacts:
            first = target_contacts[0]
            if int(first.get("use_salutation", 1)) == 0:
                return ""
            if first.get("preferred_salutation"):
                sal = first["preferred_salutation"].strip()
                if sal and not sal.endswith(("：", ":", "!", "！", ",")):
                    sal += "："
                return sal
            if len(target_contacts) == 1:
                name = first.get("name") or first.get("email", "").split("@")[0]
                return f"{name}，你好："
            names = "、".join([c.get("name") or c.get("email", "").split("@")[0] for c in target_contacts[:3]])
            return f"{names}，你们好："

        if fallback_emails:
            return f"{fallback_emails[0].split('@')[0]}，你好："
        return ""

    @classmethod
    def apply_fulltext_rewrites(
        cls,
        text: str,
        sender_name: str,
        sender_email: str = "",
        target_email: str = "",
        custom_rules: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """在纯文本全文范围内执行主语、人称及学习到的短语替换"""
        if not text:
            return ""
        clean_sender = sender_name.strip() or (sender_email.split("@")[0] if sender_email else "发件方")
        result = text

        active_rules = []
        if custom_rules:
            # 按命中使用频次 hit_count 降序排列，优先应用高频习惯规则
            sorted_custom = sorted(
                [r for r in custom_rules if r.get("is_enabled", 1)],
                key=lambda x: int(x.get("hit_count", 1)),
                reverse=True
            )
            for r in sorted_custom:
                s_filter = (r.get("sender_filter") or "").strip().lower()
                t_filter = (r.get("target_filter") or "").strip().lower()
                if s_filter and s_filter != sender_email.lower():
                    continue
                if t_filter and t_filter not in target_email.lower():
                    continue
                active_rules.append({
                    "source": r.get("source_pattern", ""),
                    "target": r.get("target_template", ""),
                    "is_regex": bool(r.get("is_regex", 0))
                })

        for d in DEFAULT_FULLTEXT_REWRITES:
            active_rules.append({"source": d["source"], "target": d["target"], "is_regex": False})

        for rule in active_rules:
            src = rule["source"]
            if not src:
                continue
            tgt = rule["target"].replace("{sender_name}", clean_sender)
            if rule["is_regex"]:
                try:
                    result = re.sub(src, tgt, result)
                except re.error:
                    pass
            else:
                result = result.replace(src, tgt)
        return result

    @classmethod
    def rewrite_html_preserving_format(
        cls,
        raw_html: str,
        sender_name: str,
        sender_email: str,
        target_email: str,
        salutation: str,
        closing_sign: str,
        custom_rules: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        直接在 HTML DOM 树上剥离原开头称呼、替换全文文本节点中的主语与人称，
        100% 保留原邮件中的表格、字体颜色、加粗与内嵌图片！
        """
        if not raw_html:
            return ""

        soup = BeautifulSoup(raw_html, "html.parser")
        body_root = soup.body if soup.body else soup

        # 1. 检查第一个非空文本节点是否为原称呼，若是则剥离
        first_text_checked = False
        for node in body_root.descendants:
            if isinstance(node, NavigableString) and node.strip():
                if not first_text_checked:
                    first_text_checked = True
                    stripped, removed = cls.strip_original_salutation_safely(str(node))
                    if removed:
                        node.replace_with(stripped)
                        break

        # 2. 遍历全文所有可见文本节点，执行主语与人称替换（不破坏 HTML 标签与表格结构）
        for node in list(body_root.descendants):
            if isinstance(node, NavigableString) and node.parent.name not in ("script", "style"):
                orig_str = str(node)
                if orig_str.strip():
                    new_str = cls.apply_fulltext_rewrites(
                        orig_str, sender_name, sender_email, target_email, custom_rules
                    )
                    if new_str != orig_str:
                        node.replace_with(new_str)

        inner_html = "".join(str(c) for c in body_root.contents)
        sal_html = f"<p style='margin:0 0 12px 0;'>{html.escape(salutation)}</p>" if salutation else ""
        close_html = f"<p style='margin:14px 0 0 0;'>{html.escape(closing_sign)}</p>" if closing_sign else ""

        return (
            f"<div style=\"font-family:'Microsoft YaHei',Segoe UI,sans-serif;font-size:14px;color:#1f2937;line-height:1.7;\">"
            f"{sal_html}{inner_html}{close_html}</div>"
        )

    @staticmethod
    def compute_recipients(
        my_email: str,
        sender_email: str,
        to_list: List[Dict[str, str]],
        cc_list: List[Dict[str, str]],
        selected_f_emails: List[str],
        include_sender_in_cc: bool = True
    ) -> Tuple[List[str], List[str]]:
        """计算收件人 F 与抄送列表（支持与原发件人 A、原抄送人实时去重并剔除自身与收件人）"""
        my_clean = (my_email or "").strip().lower()
        new_to = []
        to_seen = set()
        for f_addr in selected_f_emails:
            clean = f_addr.strip().lower()
            if clean and clean != my_clean and clean not in to_seen:
                to_seen.add(clean)
                new_to.append(f_addr.strip())

        candidates = []
        if include_sender_in_cc and sender_email:
            candidates.append(sender_email.strip())
        for item in (to_list or []):
            if item.get("email"):
                candidates.append(item["email"].strip())
        for item in (cc_list or []):
            if item.get("email"):
                candidates.append(item["email"].strip())

        new_cc = []
        cc_seen = set()
        for addr in candidates:
            clean = addr.lower()
            if not clean or clean == my_clean or clean in to_seen or clean in cc_seen:
                continue
            cc_seen.add(clean)
            new_cc.append(addr)

        return new_to, new_cc

    @classmethod
    def build_compose_content(
        cls,
        mode: str,
        email_data: Dict[str, Any],
        target_contacts: List[Dict[str, Any]],
        selected_f_emails: List[str],
        custom_rewrite_rules: Optional[List[Dict[str, Any]]] = None,
        closing_sign: str = "请协助跟进处理，谢谢！"
    ) -> Dict[str, str]:
        """构建待发邮件的完整内容（双模式：新建改写 vs 标准转发）"""
        orig_subject = (email_data.get("subject") or "").strip()
        sender_name = email_data.get("sender_name") or email_data.get("sender_email", "").split("@")[0]
        sender_email = email_data.get("sender_email", "")
        first_target_email = selected_f_emails[0] if selected_f_emails else ""

        salutation = cls.generate_target_salutation(target_contacts, selected_f_emails)
        stripped_text, _ = cls.strip_original_salutation_safely(email_data.get("body_text", ""))
        rewritten_text = cls.apply_fulltext_rewrites(
            stripped_text, sender_name, sender_email, first_target_email, custom_rewrite_rules
        )

        if mode == "rewrite_new":
            clean_subject = re.sub(r"^(Fw:|FW:|转发:|转发：)\s*", "", orig_subject, flags=re.IGNORECASE)
            parts = [p for p in (salutation, rewritten_text, closing_sign) if p.strip()]
            plain_body = "\n\n".join(parts)

            raw_html = (email_data.get("body_html") or "").strip()
            if raw_html:
                html_body = cls.rewrite_html_preserving_format(
                    raw_html, sender_name, sender_email, first_target_email,
                    salutation, closing_sign, custom_rewrite_rules
                )
            else:
                html_paragraphs = "<br>".join(html.escape(plain_body).splitlines())
                html_body = (
                    f"<div style=\"font-family:'Microsoft YaHei',Segoe UI,sans-serif;font-size:14px;"
                    f"color:#1f2937;line-height:1.7;\">{html_paragraphs}</div>"
                )
            return {
                "subject": clean_subject,
                "salutation": salutation,
                "plain_body": plain_body,
                "html_body": html_body
            }
        else:
            fw_subject = orig_subject if orig_subject.lower().startswith(("fw:", "转发:")) else f"Fw: {orig_subject}"
            top_lines = [salutation, f"{sender_name}发来以下协调事项，{closing_sign}"] if salutation else [f"{sender_name}发来以下协调事项，{closing_sign}"]
            top_comment = "\n".join(top_lines)

            sender_str = f"{email_data.get('sender_name', '')} <{email_data.get('sender_email', '')}>".strip()
            to_str = "; ".join([f"{x.get('name', '')} <{x.get('email', '')}>" for x in email_data.get("to_list", [])])
            cc_str = "; ".join([f"{x.get('name', '')} <{x.get('email', '')}>" for x in email_data.get("cc_list", [])])
            date_str = email_data.get("date_str", "")

            plain_body = (
                f"{top_comment}\n\n"
                f"------------------ 原始邮件 ------------------\n"
                f"发件人: {sender_str}\n"
                f"发送时间: {date_str}\n"
                f"收件人: {to_str}\n"
                f"抄送: {cc_str}\n"
                f"主题: {orig_subject}\n\n"
                f"{email_data.get('body_text', '')}"
            )
            comment_html = html.escape(top_comment).replace("\n", "<br>")
            orig_html = email_data.get("body_html") or f"<pre style='white-space:pre-wrap;'>{html.escape(email_data.get('body_text', ''))}</pre>"
            html_body = (
                f"<div style=\"font-family:'Microsoft YaHei',Segoe UI,sans-serif;font-size:14px;color:#1f2937;line-height:1.6;\">"
                f"<div style=\"margin-bottom:16px;\">{comment_html}</div>"
                f"<div style=\"border-top:1px solid #d1d5db;margin-top:16px;color:#4b5563;font-size:13px;background:#f9fafb;padding:10px 14px;border-radius:6px;\">"
                f"<b>------------------ 原始邮件 ------------------</b><br>"
                f"<b>发件人：</b>{html.escape(sender_str)}<br>"
                f"<b>发送时间：</b>{html.escape(date_str)}<br>"
                f"<b>收件人：</b>{html.escape(to_str)}<br>"
                f"<b>抄送：</b>{html.escape(cc_str)}<br>"
                f"<b>主题：</b>{html.escape(orig_subject)}"
                f"</div><div style=\"margin-top:14px;\">{orig_html}</div></div>"
            )
            return {
                "subject": fw_subject,
                "salutation": salutation,
                "plain_body": plain_body,
                "html_body": html_body
            }
