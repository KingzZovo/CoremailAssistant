"""Ollama local LLM client for intelligent summary extraction and full-text polishing."""

import json
import re
from typing import List, Dict, Any, Optional
import requests


class OllamaClient:
    """本地 Ollama 大模型服务客户端，具备健康检查与自动降级保障机制"""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        default_model: str = "qwen2.5:3b",
        timeout: int = 30
    ):
        self.base_url = (base_url or "http://127.0.0.1:11434").rstrip("/")
        self.default_model = default_model or "qwen2.5:3b"
        self.timeout = int(timeout or 30)

    def is_available(self) -> bool:
        """检查 Ollama 服务是否正在运行"""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def list_local_models(self) -> List[str]:
        """获取本地已下载的 Ollama 模型列表"""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                return models
        except Exception:
            pass
        return []

    def analyze_and_rewrite_email(
        self,
        email_data: Dict[str, Any],
        candidate_contacts: List[Dict[str, Any]],
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        调用大模型提取邮件核心摘要、紧急度及建议的流转对象
        """
        target_model = model or self.default_model
        contacts_desc = ", ".join([f"{c.get('name')}({c.get('email')})" for c in candidate_contacts if c.get("name")])
        sender_name = email_data.get("sender_name") or email_data.get("sender_email", "")

        prompt = f"""你是一名专业的企业邮件流转助理。请阅读以下来自【{sender_name}】的邮件全文，并按要求输出 JSON 格式分析结果：

【邮件主题】：{email_data.get('subject', '')}
【邮件正文】：
{email_data.get('body_text', '')[:2000]}

【可选联系人候选池】：
{contacts_desc}

请以严格的 JSON 格式返回以下字段（不要包含 markdown 代码块包裹之外的多余解释）：
{{
  "summary": "1~2句话提炼该邮件核心事项与诉求",
  "urgency": "高" 或 "中" 或 "普通",
  "suggested_contacts": ["推荐流转的联系人邮箱列表，优先从候选池中选"],
  "recommended_mode": "rewrite_new" 或 "standard_forward"
}}
"""
        fallback_res = {
            "summary": (email_data.get("body_text", "")[:120] + "...") if len(email_data.get("body_text", "")) > 120 else email_data.get("body_text", ""),
            "urgency": "普通",
            "suggested_contacts": [],
            "recommended_mode": "rewrite_new"
        }

        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": target_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3}
                },
                timeout=self.timeout
            )
            if resp.status_code != 200:
                return fallback_res

            raw_text = resp.json().get("response", "").strip()
            # 提取 JSON 内容
            json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                return {
                    "summary": str(parsed.get("summary") or fallback_res["summary"]),
                    "urgency": str(parsed.get("urgency") or "普通"),
                    "suggested_contacts": parsed.get("suggested_contacts") or [],
                    "recommended_mode": str(parsed.get("recommended_mode") or "rewrite_new")
                }
        except Exception:
            pass

        return fallback_res

    def polish_fulltext_html(
        self,
        raw_text: str,
        sender_name: str,
        target_salutation: str,
        model: Optional[str] = None
    ) -> str:
        """
        在富文本编辑器中调用大模型对全文人称/主语进行润色
        """
        if not raw_text:
            return ""

        target_model = model or self.default_model
        prompt = f"""你是一名邮件助理。现需要将发件人【{sender_name}】发来的邮件全文改写为发给协作同事的新邮件。
要求：
1. 称呼使用：“{target_salutation}”
2. 完整保留正文核心事实、数据与要求；
3. 将第一人称主语“我/我方/我们”平滑改写为“{sender_name}那边/发件方”；
4. 将向上的请示用语（如“请您审批”）润色为平级协作用语（如“请协助跟进处理”）；
5. 直接输出润色后的正文纯文本，不要包含任何多余解释与前缀。

【待改写原文】：
{raw_text}
"""
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": target_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3}
                },
                timeout=self.timeout
            )
            if resp.status_code == 200:
                polished = resp.json().get("response", "").strip()
                if polished:
                    return polished
        except Exception:
            pass

        return raw_text
