"""Full-text online incremental machine learning and edit Diff auto-learning engine."""

import os
import re
import difflib
from typing import Dict, Any, List, Tuple, Optional
try:
    import joblib
except Exception:
    joblib = None

try:
    import jieba
except Exception:
    jieba = None

try:
    import numpy as np
except Exception:
    np = None

try:
    from sklearn.feature_extraction.text import HashingVectorizer
    from sklearn.linear_model import SGDClassifier
    HAS_SKLEARN = True
except Exception:
    HashingVectorizer = None
    SGDClassifier = None
    HAS_SKLEARN = False

from config import ML_MODELS_PATH


class LocalEmailLearner:
    """
    基于邮件全文语义特征 + 全文编辑差异(Diff)对比的本地增量机器学习引擎。
    专为纯内网环境（10代 i5 + 16GB 内存）设计，不截断正文，直接分析邮件全文。
    若极端运行环境缺失 C 扩展依赖，自动平滑降级为内置纯 Python 词频统计预测。
    """

    def __init__(self, model_path: str = ML_MODELS_PATH):
        self.model_path = model_path
        # 使用 2^15 维特征空间，对整封邮件全文提取分词与双词共现特征
        if HAS_SKLEARN and HashingVectorizer is not None:
            try:
                self.vectorizer = HashingVectorizer(
                    n_features=2**15,
                    analyzer=self._fulltext_ngram_analyzer,
                    alternate_sign=False
                )
            except Exception:
                self.vectorizer = None
        else:
            self.vectorizer = None

        # 1. 全文是否需要流转分类器 (0: 忽略, 1: 需流转处理)
        if HAS_SKLEARN and SGDClassifier is not None:
            try:
                self.action_clf = SGDClassifier(loss="log_loss", random_state=42)
                self.mode_clf = SGDClassifier(loss="log_loss", random_state=42)
            except Exception:
                self.action_clf = None
                self.mode_clf = None
        else:
            self.action_clf = None
            self.mode_clf = None

        self.action_fitted = False
        self.mode_fitted = False

        # 3. 发件人 & 全文词组 -> 目标收件人 F 的权重统计矩阵 (纯 Python 统计，永远安全)
        self.sender_to_target_stats: Dict[str, Dict[str, float]] = {}
        self.token_to_target_stats: Dict[str, Dict[str, float]] = {}

        # 4. 细粒度转发习惯记忆矩阵（引文 vs 不引文）
        self.pair_mode_stats: Dict[str, Dict[str, int]] = {}
        self.sender_mode_stats: Dict[str, Dict[str, int]] = {}
        self.folder_mode_stats: Dict[str, Dict[str, int]] = {}
        self._load()

    @staticmethod
    def _fulltext_ngram_analyzer(text: str) -> List[str]:
        """对邮件全文进行中文分词，并同时生成 Unigram（单词）与 Bigram（相邻双词短语）特征"""
        if not text:
            return []
        words = []
        try:
            if jieba is not None:
                words = [w.strip().lower() for w in jieba.lcut(text) if len(w.strip()) >= 2]
        except Exception:
            words = []
        if not words:
            # 纯 Python 降级正则分词 (提取连续中文或英文词组)
            words = [w.strip().lower() for w in re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z0-9_-]{2,}", text)]
        bigrams = [f"{words[i]}_{words[i+1]}" for i in range(len(words) - 1)]
        return words + bigrams

    @staticmethod
    def _build_full_feature_text(
        sender_email: str,
        cc_list: List[Dict[str, str]],
        subject: str,
        full_body: str,
        folder_name: str = "",
        to_list: Optional[List[Dict[str, str]]] = None,
        attachments: Optional[List[Any]] = None,
        my_email: str = ""
    ) -> str:
        """
        全方位特征融合：
        - 权重强化发件人特征: __from_{sender_email}__ (x3)
        - 权重强化所属文件夹特征: __folder_{folder_name}__ (x2)
        - 我是否在 To 或 CC: __me_in_to__ / __me_in_cc__
        - 附件特征: __has_attach__
        - 主题与邮件全文 (不截断)
        """
        sender_clean = sender_email.lower().strip()
        sender_tag = f"__from_{sender_clean}__" if sender_clean else ""
        folder_clean = folder_name.strip()
        folder_tag = f"__folder_{folder_clean}__" if folder_clean else ""

        tags = []
        if sender_tag:
            tags.extend([sender_tag, sender_tag, sender_tag])
        if folder_tag:
            tags.extend([folder_tag, folder_tag])

        my_clean = my_email.lower().strip()
        if my_clean:
            in_to = any(my_clean in str(t.get("email", "")).lower() for t in (to_list or []))
            in_cc = any(my_clean in str(c.get("email", "")).lower() for c in (cc_list or []))
            if in_to:
                tags.append("__me_in_to__")
            if in_cc:
                tags.append("__me_in_cc__")

        if attachments:
            tags.append("__has_attach__")

        for c in (cc_list or []):
            ce = str(c.get("email", "")).lower().strip()
            if ce:
                tags.append(f"__cc_{ce}__")

        tag_str = " ".join(tags)
        return f"{tag_str} {subject} {subject} {full_body or ''}"

    def predict_email(
        self,
        email_data: Dict[str, Any],
        candidate_contacts: Optional[List[Dict[str, Any]]] = None,
        my_email: str = ""
    ) -> Dict[str, Any]:
        """基于邮件全文预测：是否需流转、推荐新建还是转发、推荐收件人 F"""
        if candidate_contacts is None:
            candidate_contacts = []
        sender = (email_data.get("sender_email") or "").lower().strip()
        cc_list = email_data.get("cc_list") or []
        to_list = email_data.get("to_list") or []
        subject = email_data.get("subject") or ""
        full_body = email_data.get("body_text") or ""
        folder_name = email_data.get("folder_name") or ""
        attachments = email_data.get("attachments") or []

        feat_text = self._build_full_feature_text(
            sender, cc_list, subject, full_body,
            folder_name=folder_name, to_list=to_list, attachments=attachments, my_email=my_email
        )

        need_prob = 0.5
        if self.vectorizer and self.action_clf and self.action_fitted:
            try:
                X = self.vectorizer.transform([feat_text])
                need_prob = float(self.action_clf.predict_proba(X)[0][1])
            except Exception:
                need_prob = 0.5

        # 计算收件人 F 得分
        scores: Dict[str, float] = {}
        valid_emails = {c["email"].lower(): c["email"] for c in candidate_contacts if c.get("email")}

        if sender in self.sender_to_target_stats:
            for f_mail, weight in self.sender_to_target_stats[sender].items():
                if f_mail in valid_emails:
                    scores[valid_emails[f_mail]] = scores.get(valid_emails[f_mail], 0.0) + weight * 3.0

        full_tokens = set(self._fulltext_ngram_analyzer(f"{subject} {full_body}"))
        for tk in full_tokens:
            if tk in self.token_to_target_stats:
                for f_mail, weight in self.token_to_target_stats[tk].items():
                    if f_mail in valid_emails:
                        scores[valid_emails[f_mail]] = scores.get(valid_emails[f_mail], 0.0) + weight * 0.4

        ranked_f = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
        top_f = ranked_f[0].lower().strip() if ranked_f else ""

        # 模式推荐：优先 (sender, top_f) 习惯 -> 其次 sender 习惯 -> 其次 folder 习惯 -> 模式分类器
        rec_mode = None
        if sender and top_f:
            pair_key = f"{sender}::{top_f}"
            if pair_key in self.pair_mode_stats:
                p_stats = self.pair_mode_stats[pair_key]
                if p_stats.get("rewrite_new", 0) > p_stats.get("standard_forward", 0):
                    rec_mode = "rewrite_new"
                elif p_stats.get("standard_forward", 0) > p_stats.get("rewrite_new", 0):
                    rec_mode = "standard_forward"

        if not rec_mode and sender and sender in self.sender_mode_stats:
            s_stats = self.sender_mode_stats[sender]
            if s_stats.get("rewrite_new", 0) > s_stats.get("standard_forward", 0):
                rec_mode = "rewrite_new"
            elif s_stats.get("standard_forward", 0) > s_stats.get("rewrite_new", 0):
                rec_mode = "standard_forward"

        if not rec_mode and folder_name and folder_name in self.folder_mode_stats:
            f_stats = self.folder_mode_stats[folder_name]
            if f_stats.get("rewrite_new", 0) > f_stats.get("standard_forward", 0):
                rec_mode = "rewrite_new"
            elif f_stats.get("standard_forward", 0) > f_stats.get("rewrite_new", 0):
                rec_mode = "standard_forward"

        if not rec_mode:
            if self.vectorizer and self.mode_clf and self.mode_fitted:
                try:
                    X = self.vectorizer.transform([feat_text])
                    m_prob = float(self.mode_clf.predict_proba(X)[0][1])
                    rec_mode = "rewrite_new" if m_prob >= 0.5 else "standard_forward"
                except Exception:
                    rec_mode = "rewrite_new"
            else:
                rec_mode = "rewrite_new"

        return {
            "need_action_prob": round(need_prob, 3),
            "is_ml_recommended": need_prob >= 0.55,
            "recommended_mode": rec_mode,
            "predicted_f_emails": ranked_f[:2]
        }

    def learn_from_user_action(
        self,
        email_data: Dict[str, Any],
        action_label: int,
        chosen_mode: str = "rewrite_new",
        chosen_f_emails: Optional[List[str]] = None,
        my_email: str = ""
    ) -> None:
        """从用户对整封邮件的实际操作中进行全文特征增量训练"""
        sender = (email_data.get("sender_email") or "").lower().strip()
        cc_list = email_data.get("cc_list") or []
        to_list = email_data.get("to_list") or []
        subject = email_data.get("subject") or ""
        full_body = email_data.get("body_text") or ""
        folder_name = email_data.get("folder_name") or ""
        attachments = email_data.get("attachments") or []

        feat_text = self._build_full_feature_text(
            sender, cc_list, subject, full_body,
            folder_name=folder_name, to_list=to_list, attachments=attachments, my_email=my_email
        )
        if self.vectorizer and self.action_clf and np is not None:
            try:
                X = self.vectorizer.transform([feat_text])
                y_action = np.array([1 if action_label else 0])
                self.action_clf.partial_fit(X, y_action, classes=np.array([0, 1]))
                self.action_fitted = True

                if action_label == 1 and self.mode_clf:
                    y_mode = np.array([1 if chosen_mode == "rewrite_new" else 0])
                    self.mode_clf.partial_fit(X, y_mode, classes=np.array([0, 1]))
                    self.mode_fitted = True
            except Exception:
                pass

        if action_label == 1:
            full_tokens = set(self._fulltext_ngram_analyzer(f"{subject} {full_body}"))
            for f_addr in (chosen_f_emails or []):
                f_clean = f_addr.lower().strip()
                if not f_clean:
                    continue
                if sender:
                    self.sender_to_target_stats.setdefault(sender, {})
                    self.sender_to_target_stats[sender][f_clean] = self.sender_to_target_stats[sender].get(f_clean, 0.0) + 1.0

                    pair_key = f"{sender}::{f_clean}"
                    self.pair_mode_stats.setdefault(pair_key, {"rewrite_new": 0, "standard_forward": 0})
                    self.pair_mode_stats[pair_key][chosen_mode] = self.pair_mode_stats[pair_key].get(chosen_mode, 0) + 1

                for tk in full_tokens:
                    self.token_to_target_stats.setdefault(tk, {})
                    self.token_to_target_stats[tk][f_clean] = self.token_to_target_stats[tk].get(f_clean, 0.0) + 1.0

            if sender:
                self.sender_mode_stats.setdefault(sender, {"rewrite_new": 0, "standard_forward": 0})
                self.sender_mode_stats[sender][chosen_mode] = self.sender_mode_stats[sender].get(chosen_mode, 0) + 1

            if folder_name:
                self.folder_mode_stats.setdefault(folder_name, {"rewrite_new": 0, "standard_forward": 0})
                self.folder_mode_stats[folder_name][chosen_mode] = self.folder_mode_stats[folder_name].get(chosen_mode, 0) + 1

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

    # 兼容别名
    predict = predict_email
    learn_from_sent_email = learn_from_user_action
    learn_rewrite_rule_from_diff = extract_fulltext_rewrite_diffs

    def reset_models(self) -> None:
        """重置本地机器学习模型"""
        if HAS_SKLEARN and SGDClassifier is not None:
            try:
                self.action_clf = SGDClassifier(loss="log_loss", random_state=42)
                self.mode_clf = SGDClassifier(loss="log_loss", random_state=42)
            except Exception:
                self.action_clf = None
                self.mode_clf = None
        else:
            self.action_clf = None
            self.mode_clf = None
        self.action_fitted = False
        self.mode_fitted = False
        self.sender_to_target_stats = {}
        self.token_to_target_stats = {}
        self.pair_mode_stats = {}
        self.sender_mode_stats = {}
        self.folder_mode_stats = {}
        if os.path.exists(self.model_path):
            try:
                os.remove(self.model_path)
            except Exception:
                pass

    def _save(self) -> None:
        """持久化保存模型状态"""
        if joblib is None:
            return
        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            joblib.dump({
                "action_clf": self.action_clf,
                "action_fitted": self.action_fitted,
                "mode_clf": self.mode_clf,
                "mode_fitted": self.mode_fitted,
                "sender_stats": self.sender_to_target_stats,
                "token_stats": self.token_to_target_stats,
                "pair_mode_stats": self.pair_mode_stats,
                "sender_mode_stats": self.sender_mode_stats,
                "folder_mode_stats": self.folder_mode_stats,
            }, self.model_path)
        except Exception:
            pass

    def _load(self) -> None:
        """加载已持久化的模型"""
        if joblib is None or not os.path.isfile(self.model_path):
            return
        try:
            data = joblib.load(self.model_path)
            if self.action_clf is not None:
                self.action_clf = data.get("action_clf", self.action_clf)
            self.action_fitted = data.get("action_fitted", False)
            if self.mode_clf is not None:
                self.mode_clf = data.get("mode_clf", self.mode_clf)
            self.mode_fitted = data.get("mode_fitted", False)
            self.sender_to_target_stats = data.get("sender_stats", {})
            self.token_to_target_stats = data.get("token_stats", {})
            self.pair_mode_stats = data.get("pair_mode_stats", {})
            self.sender_mode_stats = data.get("sender_mode_stats", {})
            self.folder_mode_stats = data.get("folder_mode_stats", {})
        except Exception:
            pass

