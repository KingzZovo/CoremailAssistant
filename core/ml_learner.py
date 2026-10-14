"""Full-text online incremental machine learning and edit Diff auto-learning engine."""

import os
import re
import difflib
from typing import Dict, Any, List, Tuple, Optional
import joblib
import jieba
import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.linear_model import SGDClassifier

from config import ML_MODELS_PATH


class LocalEmailLearner:
    """
    基于邮件全文语义特征 + 全文编辑差异(Diff)对比的本地增量机器学习引擎。
    专为纯内网环境（10代 i5 + 16GB 内存）设计，不截断正文，直接分析邮件全文。
    """

    def __init__(self, model_path: str = ML_MODELS_PATH):
        self.model_path = model_path
        # 使用 2^15 维特征空间，对整封邮件全文提取分词与双词共现特征
        self.vectorizer = HashingVectorizer(
            n_features=2**15,
            analyzer=self._fulltext_ngram_analyzer,
            alternate_sign=False
        )
        # 1. 全文是否需要流转分类器 (0: 忽略, 1: 需流转处理)
        self.action_clf = SGDClassifier(loss="log_loss", random_state=42)
        self.action_fitted = False

        # 2. 全文流转方式分类器 (0: standard_forward 标准转发, 1: rewrite_new 改写新建邮件)
        self.mode_clf = SGDClassifier(loss="log_loss", random_state=42)
        self.mode_fitted = False

        # 3. 发件人 & 全文词组 -> 目标收件人 F 的权重统计矩阵
        self.sender_to_target_stats: Dict[str, Dict[str, float]] = {}
        self.token_to_target_stats: Dict[str, Dict[str, float]] = {}
        self._load()

    @staticmethod
    def _fulltext_ngram_analyzer(text: str) -> List[str]:
        """对邮件全文进行中文分词，并同时生成 Unigram（单词）与 Bigram（相邻双词短语）特征"""
        if not text:
            return []
        words = [w.strip().lower() for w in jieba.lcut(text) if len(w.strip()) >= 2]
        bigrams = [f"{words[i]}_{words[i+1]}" for i in range(len(words) - 1)]
        return words + bigrams

    @staticmethod
    def _build_full_feature_text(sender_email: str, cc_list: List[Dict[str, str]], subject: str, full_body: str) -> str:
        """融合发件人、原抄送人特征、主题与整封邮件全文（不截断）"""
        sender_tag = f"__from_{sender_email.lower().strip()}__"
        cc_tags = " ".join([f"__cc_{c.get('email', '').lower().strip()}__" for c in (cc_list or [])])
        return f"{sender_tag} {sender_tag} {cc_tags} {subject} {subject} {full_body or ''}"

    def predict_email(self, email_data: Dict[str, Any], candidate_contacts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """基于邮件全文预测：是否需流转、推荐新建还是转发、推荐收件人 F"""
        sender = (email_data.get("sender_email") or "").lower().strip()
        cc_list = email_data.get("cc_list") or []
        subject = email_data.get("subject") or ""
        full_body = email_data.get("body_text") or ""

        feat_text = self._build_full_feature_text(sender, cc_list, subject, full_body)
        X = self.vectorizer.transform([feat_text])

        need_prob = 0.5
        if self.action_fitted:
            try:
                need_prob = float(self.action_clf.predict_proba(X)[0][1])
            except Exception:
                need_prob = 0.5

        rec_mode = "rewrite_new"
        if self.mode_fitted:
            try:
                m_prob = float(self.mode_clf.predict_proba(X)[0][1])
                rec_mode = "rewrite_new" if m_prob >= 0.5 else "standard_forward"
            except Exception:
                rec_mode = "rewrite_new"

        scores: Dict[str, float] = {}
        valid_emails = {c["email"].lower(): c["email"] for c in candidate_contacts if c.get("email")}

        if sender in self.sender_to_target_stats:
            for f_mail, weight in self.sender_to_target_stats[sender].items():
                if f_mail in valid_emails:
                    scores[valid_emails[f_mail]] = scores.get(valid_emails[f_mail], 0.0) + weight * 3.0

        # 扫描整封邮件全文的词与双词短语计算收件人 F 匹配得分
        full_tokens = set(self._fulltext_ngram_analyzer(f"{subject} {full_body}"))
        for tk in full_tokens:
            if tk in self.token_to_target_stats:
                for f_mail, weight in self.token_to_target_stats[tk].items():
                    if f_mail in valid_emails:
                        scores[valid_emails[f_mail]] = scores.get(valid_emails[f_mail], 0.0) + weight * 0.4

        ranked_f = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
        return {
            "need_action_prob": round(need_prob, 3),
            "is_ml_recommended": need_prob >= 0.58,
            "recommended_mode": rec_mode,
            "predicted_f_emails": ranked_f[:2]
        }

    def learn_from_user_action(
        self,
        email_data: Dict[str, Any],
        action_label: int,
        chosen_mode: str = "rewrite_new",
        chosen_f_emails: Optional[List[str]] = None
    ) -> None:
        """从用户对整封邮件的实际操作中进行全文特征增量训练"""
        sender = (email_data.get("sender_email") or "").lower().strip()
        cc_list = email_data.get("cc_list") or []
        subject = email_data.get("subject") or ""
        full_body = email_data.get("body_text") or ""

        feat_text = self._build_full_feature_text(sender, cc_list, subject, full_body)
        X = self.vectorizer.transform([feat_text])

        y_action = np.array([1 if action_label else 0])
        self.action_clf.partial_fit(X, y_action, classes=np.array([0, 1]))
        self.action_fitted = True

        if action_label == 1:
            y_mode = np.array([1 if chosen_mode == "rewrite_new" else 0])
            self.mode_clf.partial_fit(X, y_mode, classes=np.array([0, 1]))
            self.mode_fitted = True

            full_tokens = set(self._fulltext_ngram_analyzer(f"{subject} {full_body}"))
            for f_addr in (chosen_f_emails or []):
                f_clean = f_addr.lower().strip()
                if not f_clean:
                    continue
                if sender:
                    self.sender_to_target_stats.setdefault(sender, {})
                    self.sender_to_target_stats[sender][f_clean] = self.sender_to_target_stats[sender].get(f_clean, 0.0) + 1.0
                for tk in full_tokens:
                    self.token_to_target_stats.setdefault(tk, {})
                    self.token_to_target_stats[tk][f_clean] = self.token_to_target_stats[tk].get(f_clean, 0.0) + 1.0

        self._save()

    @staticmethod
    def extract_fulltext_rewrite_diffs(
        original_full_text: str,
        edited_full_text: str,
        sender_name: str
    ) -> List[Tuple[str, str]]:
        """
        全文级修改差异自学习器：
        对比【原邮件全文】与【用户在富文本编辑器中修改后的全文】，
        按分句对比提取用户在正文任意段落手动修改的短语替换对 (source_phrase -> target_phrase)。
        例如用户在正文第3段把 "我部申请开通" 改成了 "研发部申请开通"，系统会自动捕捉该替换对！
        """
        if not original_full_text or not edited_full_text:
            return []

        orig_sents = [s.strip() for s in re.split(r"[。！？!?\n；;]", original_full_text) if s.strip()]
        edit_sents = [s.strip() for s in re.split(r"[。！？!?\n；;]", edited_full_text) if s.strip()]

        learned_pairs: List[Tuple[str, str]] = []
        matcher = difflib.SequenceMatcher(None, orig_sents, edit_sents)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                for s_orig in orig_sents[i1:i2]:
                    best_edit = None
                    best_sim = 0.0
                    for s_edit in edit_sents[j1:j2]:
                        sim = difflib.SequenceMatcher(None, s_orig, s_edit).ratio()
                        if sim > best_sim:
                            best_sim = sim
                            best_edit = s_edit
                    if 0.40 <= best_sim <= 0.98 and best_edit:
                        char_matcher = difflib.SequenceMatcher(None, s_orig, best_edit)
                        for c_tag, ci1, ci2, cj1, cj2 in char_matcher.get_opcodes():
                            if c_tag == "replace":
                                src_piece = s_orig[ci1:ci2].strip()
                                tgt_piece = best_edit[cj1:cj2].strip()
                                if 1 <= len(src_piece) <= 12 and 1 <= len(tgt_piece) <= 18 and src_piece != tgt_piece:
                                    if sender_name and sender_name in tgt_piece:
                                        tgt_piece = tgt_piece.replace(sender_name, "{sender_name}")
                                    if (src_piece, tgt_piece) not in learned_pairs:
                                        learned_pairs.append((src_piece, tgt_piece))

        return learned_pairs

    def reset_models(self) -> None:
        """重置本地机器学习模型"""
        self.action_clf = SGDClassifier(loss="log_loss", random_state=42)
        self.action_fitted = False
        self.mode_clf = SGDClassifier(loss="log_loss", random_state=42)
        self.mode_fitted = False
        self.sender_to_target_stats = {}
        self.token_to_target_stats = {}
        if os.path.exists(self.model_path):
            try:
                os.remove(self.model_path)
            except Exception:
                pass

    def _save(self) -> None:
        """持久化保存模型状态"""
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        joblib.dump({
            "action_clf": self.action_clf,
            "action_fitted": self.action_fitted,
            "mode_clf": self.mode_clf,
            "mode_fitted": self.mode_fitted,
            "sender_stats": self.sender_to_target_stats,
            "token_stats": self.token_to_target_stats
        }, self.model_path)

    def _load(self) -> None:
        """加载已持久化的模型"""
        if not os.path.isfile(self.model_path):
            return
        try:
            data = joblib.load(self.model_path)
            self.action_clf = data.get("action_clf", self.action_clf)
            self.action_fitted = data.get("action_fitted", False)
            self.mode_clf = data.get("mode_clf", self.mode_clf)
            self.mode_fitted = data.get("mode_fitted", False)
            self.sender_to_target_stats = data.get("sender_stats", {})
            self.token_to_target_stats = data.get("token_stats", {})
        except Exception:
            pass
