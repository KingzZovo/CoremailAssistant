# GitHub 仓库 `KingzZovo/CoremailAssistant` 代码审查报告与一键修复方案

我已完整审阅了你在 GitHub 上的公开仓库 [KingzZovo/CoremailAssistant](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2FKingzZovo%2FCoremailAssistant) 的全部目录与源代码（包含 `main.py`、`config.py`、`core/` 下 6 个模块、`ui/` 下 7 个模块及 `一键安装并启动.bat`）。

## 一、 总体评价：架构完成度 90%，但存在“分步生成导致的跨文件方法名不一致”

3.8 Flash 把整个项目的架子搭得非常完整（甚至在 `main.py` 中还主动加上了 `QLocalServer` 单实例运行锁，防止重复双开），核心算法如 **GB18030/UTF-8 邮件头解码**、**HTML 富文本树保留格式改写**、**剪贴板截图粘贴转 Base64/CID**、**全文 N-Gram 机器学习** 都已实现。

但是，由于大模型是分步生成不同文件的，它在写第 1 步 `core/database.py` 时用了一套函数命名，而在写第 3~5 步 `core/worker_threads.py` 和 `ui/*.py` 时又按另一套函数名去调用，导致直接运行 `python main.py` 时会触发 **`AttributeError` 崩溃**。

---

## 二、 查出的 5 处具体代码缺陷清单

| 缺陷编号 | 所在文件 | 具体问题描述 | 触发后果 |
| :--- | :--- | :--- | :--- |
| **Bug 1（致命）** | `core/database.py` | **缺失 `settings` 表的读写方法**：`main_window.py`、`settings_dialog.py`、`worker_threads.py` 均调用了 `db.get_all_settings()`、`db.get_setting(key, default)`、`db.save_setting(key, val)` 和 `db.save_settings(dict)`，但 `database.py` 中漏写了这组方法。 | 程序启动读取配置或点击“系统设置”时直接报 `AttributeError` |
| **Bug 2（致命）** | `core/database.py` 与 `core/worker_threads.py` / `ui/` | **数据库 CRUD 方法名跨文件不一致**：<br>• 调用方写 `db.get_all_contacts()`，但 `database.py` 定义的是 `get_contacts()`<br>• 调用方写 `db.get_all_match_rules(enabled_only=True)`，但 `database.py` 定义的是 `get_rules()`（且未接收 `enabled_only` 参数）<br>• 调用方写 `db.insert_email(em)`，但 `database.py` 定义的是 `save_email(email_data)` | 点击“立即同步邮件”或打开“发信确认弹窗”时报错崩溃 |
| **Bug 3（高危）** | `core/database.py` | **缺失机器学习回写数据库的方法**：发信成功后，`worker_threads.py` 会调用 `db.upsert_learned_rewrite_rule(...)`、`db.update_contact_habit(...)`、`db.increment_contact_send_count(...)` 来保存全文 Diff 习得的改写规则和称呼习惯，但 `database.py` 中未定义这三个方法。 | 邮件能发出去，但发送完成后的自学习保存阶段会抛异常 |
| **Bug 4（中危）** | `core/ml_learner.py` 与 `core/rewriter_engine.py` | **类名与方法名轻微不一致**：<br>• `rewriter_engine.py` 中方法名为 `calculate_recipients_and_cc`，而部分 UI 调用了 `compute_recipients`；同时需确保同时导出 `RewriterEngine` 与 `EmailRewriterEngine` 两个类名别名。<br>• `ml_learner.py` 中需同时兼容 `predict_email` / `predict` 以及 `learn_from_user_action` / `learn_from_sent_email`。 | 切换收件人重算抄送栏或触发机器学习预测时可能报 `AttributeError` |
| **Bug 5（工程）** | `一键安装并启动.bat` & `src/` | 1. `一键安装并启动.bat` 直接执行在线 `pip install -r requirements.txt`，拷入**纯内网**后会因无外网而失败；<br>2. 仓库根目录下的 `src/coremail_processor/` 是早期残留的另一套空壳结构，与主程序 `core/` + `ui/` 无关，容易混淆。 | 内网无法直接通过 bat 安装依赖；仓库目录显得冗余 |

---

## 三、 最快修复方式：复制这段“一键修复 Prompt”发给你的 Agent

你不需要手动去改几十处调用，只需要把下面这段 **“跨文件接口对齐与兼容层修复 Prompt”** 直接发给你的编码 Agent（让它在仓库里修改 `core/database.py`、`core/rewriter_engine.py`、`core/ml_learner.py` 并清理冗余），**1 轮对话即可彻底修好所有 Bug**：

```text
请帮我修复当前仓库中的跨文件方法名不一致与缺失方法问题（不要删减现有逻辑，通过补齐缺失方法与添加兼容别名方法来确保所有 UI 和 Worker 线程调用 100% 匹配）：

1. 修复 `core/database.py` 中的 `DatabaseManager` 类：
   - 确保 `init_db` 中创建了 `settings`、`emails`、`memos`、`contacts`、`fulltext_rewrite_rules`、`ml_training_samples`、`match_rules` 全部 7 张表。
   - 补齐配置读写方法（若数据库无值则回退读取 `config.DEFAULT_SETTINGS`）：
     - `get_all_settings(self) -> dict` 及别名 `get_settings(self) -> dict`
     - `get_setting(self, key: str, default=None)`
     - `save_setting(self, key: str, value: Any)`
     - `save_settings(self, settings_dict: dict)`
   - 为现有方法添加完整的兼容别名（确保不同模块不管用哪个名字调用都能正常工作）：
     - 联系人：`get_contacts(self)` 与 `get_all_contacts(self)` 与 `list_contacts(self)` 互通；`add_contact` 与 `upsert_contact` 互通。
     - 匹配规则：`get_rules(self, enabled_only: bool = False)` 与 `get_all_match_rules(self, enabled_only: bool = False)` 与 `list_rules(self, enabled_only: bool = False)` 互通（支持 `enabled_only` 参数过滤）。
     - 邮件存取：`save_email(self, email_data: dict)` 与 `insert_email(self, email_data: dict)` 互通；`get_existing_uids(self) -> set` 返回所有已存邮件的 `uid` 集合；`get_emails` 与 `list_emails` 与 `get_matched_emails` 互通；补齐 `update_email_status(self, uid: str, status: str, processed_at: str = "")`。
     - 备忘录：`get_memos` 与 ` get_all_memos` 与 `list_memos` 互通；`add_memo` 与 `save_memo` 与 `create_or_update_memo` 互通；补齐 `get_due_memos(self)` 与 `mark_memo_reminded(self, memo_id: int)`。
   - 补齐自学习回写数据库的 4 个方法：
     - `upsert_learned_rewrite_rule(self, sender_filter: str, target_filter: str, source_pattern: str, target_template: str, is_regex: int = 0)`：若 `(sender_filter, target_filter, source_pattern)` 已存在则 `hit_count = hit_count + 1` 并更新 `target_template`，否则插入新行（`learned_from_diff=1`）。
     - `get_active_rewrite_rules(self, sender_email: str = "", target_email: str = "") -> list` 及别名 `list_rewrite_rules(self)`。
     - `update_contact_habit(self, email: str, salutation: str = None, use_salutation: int = None, mode: str = None)`：更新对应联系人的 `preferred_salutation`、`use_salutation`、`preferred_mode`。
     - `increment_contact_send_count(self, email: str)`：将对应联系人的 `send_count` 加 1。

2. 修复 `core/rewriter_engine.py`：
   - 在文件末尾添加别名 `RewriterEngine = EmailRewriterEngine`（或反之），确保无论导入 `RewriterEngine` 还是 `EmailRewriterEngine` 均不报错。
   - 确保类中同时提供 `compute_recipients` 和 `calculate_recipients_and_cc` 两个同名指向的方法。

3. 修复 `core/ml_learner.py`：
   - 确保 `LocalEmailLearner` 类中同时提供：
     - `predict_email(self, email_data: dict, candidate_contacts: list = None)` 与兼容别名 `predict(self, ...)`
     - `learn_from_user_action(self, email_data: dict, action_label: int, chosen_mode: str = "rewrite_new", chosen_f_emails: list = None)` 与兼容别名 `learn_from_sent_email(...)`
     - `extract_fulltext_rewrite_diffs(...)` 与兼容别名 `learn_rewrite_rule_from_diff(...)`。

4. 编写一个自检脚本 `scripts/verify_imports_and_calls.py` 并运行：
   - 自动导入 `config`、`core.*`、`ui.*` 所有模块；
   - 实例化 `DatabaseManager`、`LocalEmailLearner`、`RewriterEngine`，自动调用上述所有关键方法验证无 `AttributeError` 或 SQL 语法错误。
```

---

## 四、 `core/database.py` 缺失的兼容层核心补丁代码（可直接参考）

如果你希望手动查看或直接贴入 `core/database.py` 的 `DatabaseManager` 类中，以下是补齐所有缺失接口与别名的标准实现片段：

```python
    # ==================== Settings 配置表读写 ====================
    def get_all_settings(self) -> Dict[str, Any]:
        from config import DEFAULT_SETTINGS
        merged = dict(DEFAULT_SETTINGS)
        with self._lock, self.get_connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            for r in rows:
                k, v = r["key"], r["value"]
                try:
                    merged[k] = json.loads(v)
                except Exception:
                    merged[k] = v
        return merged

    get_settings = get_all_settings

    def get_setting(self, key: str, default: Any = None) -> Any:
        all_cfg = self.get_all_settings()
        return all_cfg.get(key, default)

    def save_setting(self, key: str, value: Any) -> None:
        val_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        with self._lock, self.get_connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, val_str)
            )
            conn.commit()

    def save_settings(self, data: Dict[str, Any]) -> None:
        for k, v in data.items():
            self.save_setting(k, v)

    # ==================== 全文改写规则与联系人习惯自学习 ====================
    def upsert_learned_rewrite_rule(
        self,
        sender_filter: str,
        target_filter: str,
        source_pattern: str,
        target_template: str,
        is_regex: int = 0
    ) -> None:
        if not source_pattern or source_pattern == target_template:
            return
        with self._lock, self.get_connection() as conn:
            row = conn.execute(
                "SELECT id, hit_count FROM fulltext_rewrite_rules "
                "WHERE sender_filter = ? AND target_filter = ? AND source_pattern = ?",
                (sender_filter or "", target_filter or "", source_pattern)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE fulltext_rewrite_rules SET target_template = ?, hit_count = hit_count + 1, is_enabled = 1 WHERE id = ?",
                    (target_template, row["id"])
                )
            else:
                conn.execute(
                    "INSERT INTO fulltext_rewrite_rules "
                    "(sender_filter, target_filter, source_pattern, target_template, is_regex, learned_from_diff, hit_count, is_enabled) "
                    "VALUES (?, ?, ?, ?, ?, 1, 1, 1)",
                    (sender_filter or "", target_filter or "", source_pattern, target_template, int(is_regex))
                )
            conn.commit()

    def update_contact_habit(
        self,
        email_addr: str,
        salutation: Optional[str] = None,
        use_salutation: Optional[int] = None,
        mode: Optional[str] = None
    ) -> None:
        if not email_addr:
            return
        with self._lock, self.get_connection() as conn:
            row = conn.execute("SELECT id FROM contacts WHERE LOWER(email) = LOWER(?)", (email_addr.strip(),)).fetchone()
            if not row:
                return
            cid = row["id"]
            if salutation is not None:
                conn.execute("UPDATE contacts SET preferred_salutation = ? WHERE id = ?", (salutation, cid))
            if use_salutation is not None:
                conn.execute("UPDATE contacts SET use_salutation = ? WHERE id = ?", (int(use_salutation), cid))
            if mode is not None:
                conn.execute("UPDATE contacts SET preferred_mode = ? WHERE id = ?", (mode, cid))
            conn.commit()

    def increment_contact_send_count(self, email_addr: str) -> None:
        if not email_addr:
            return
        with self._lock, self.get_connection() as conn:
            conn.execute(
                "UPDATE contacts SET send_count = COALESCE(send_count, 0) + 1 WHERE LOWER(email) = LOWER(?)",
                (email_addr.strip(),)
            )
            conn.commit()

    # ==================== 跨模块方法名兼容别名 ====================
    def get_all_contacts(self) -> List[Dict[str, Any]]:
        return self.get_contacts()

    def get_all_match_rules(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        rules = self.get_rules()
        if enabled_only:
            return [r for r in rules if int(r.get("is_enabled", 1)) == 1]
        return rules

    def insert_email(self, email_data: Dict[str, Any]) -> bool:
        return self.save_email(email_data)
```
