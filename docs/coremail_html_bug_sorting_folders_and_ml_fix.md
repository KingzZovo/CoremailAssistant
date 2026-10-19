# 六大实机问题精准修复方案：修复“网盘文件下载”HTML源码正文、首次收信闪退、文件夹分类导航、按时间从新到旧排序、双向标记与全面机器学习

你发来的这张照片（显示 `<!DOCTYPE html>...<title>网盘文件下载</title>`）直接帮我们锁定了为什么所有邮件正文都显示异常的核心 Bug！同时，你提出的**【全部邮件】只显示“📌 标记为待流转”、【待流转邮件】只显示“🚫 无需流转”**的交互逻辑非常清晰、完全符合实际工作流。

下面为你逐一说明这 6 个问题的根因，并提供直接复制给 Agent 的一键修复 Prompt。

---

## 一、 六大问题根因诊断与升级设计

| 序号 | 你反馈的问题与需求 | 精确根因定位 / 升级方案 |
| :--- | :--- | :--- |
| **1** | **每封邮件正文都显示照片里的 `<!DOCTYPE html>...<title>网盘文件下载</title>` 源码** | **真相水落石出**：之前代码在尝试获取原始邮件时，优先请求了 `/coremail/XT5/jsp/download.jsp`（或 `/coremail/s/eml`）。在你的 Coremail XT 系统中，这个 URL 其实是**网盘下载页面的前端 HTML 外壳**（返回状态码也是 200）。代码没有检查返回内容是不是网页，直接把这段没有邮件头的 HTML 网页塞进了 `_parse_raw_email`，结果 Python 的 `email` 库把整段网页源码当成了纯文本邮件正文存入了数据库，导致后面真正的 JSON 读信接口 `mbox:readMessage` 根本没被调用！<br>**修复**：① 移除错误的 `download.jsp`，改用 Coremail 真正的读信接口 `POST /coremail/s/json?sid={sid}&func=mbox:readMessage` 和流接口 `GET /coremail/s?func=mbox:getMessageData&sid={sid}&mid={mid}&mode=html`；② 启动时自动清理数据库中已被“网盘文件下载”污染的邮件正文并重新拉取。 |
| **2** | **配置完第一次收信还是会闪退** | **根因**：在 PyInstaller 打包后的 Windows 环境中，`QThread` 子线程默认栈空间较小；配置保存后第一次启动 `MailSyncWorker` 子线程时，在子线程内首次冷启动加载 `jieba` 大词典和 `sklearn` 模型（或 `SettingsDialog` 测试连接的残留线程未退出就销毁窗口），触发底层 C 栈溢出或 `qFatal` 闪退（第二次启动因为有了 `jieba.cache` 缓存所以不闪退）。<br>**修复**：在程序启动的**主线程**中提前预热加载 `jieba.initialize()` 与机器学习模型，并在设置窗口关闭 300ms 后再延迟启动同步线程。 |
| **3** | **全部邮件没有带出账号里的文件夹，所有邮件堆在一起** | **根因**：虽然拉取时扫描了多个文件夹，但 UI 界面没有做**文件夹分类筛选栏**，所有邮件全混在一个列表里。<br>**修复**：在邮件列表顶部（及左侧）增加 **【📁 文件夹切换栏】**（如：`全部文件夹`、`收件箱`、`自定义文件夹A`、`自定义文件夹B`...），点击即可按文件夹独立查看邮件。 |
| **4** | **邮件没有按收信时间从新到旧排序，顺序很乱** | **根因**：① 多个文件夹依次拉取后是按文件夹顺序入库的；② 原邮件的 `date_str` 有的是英文格式（如 `Mon, 19 Oct 2026...`），有的是毫秒时间戳，直接用字符串排序完全是乱序。<br>**修复**：新增整数时间戳字段 `received_timestamp` 和统一格式时间 `YYYY-MM-DD HH:MM:SS`，解析所有日期格式转为精确秒级时间戳，所有列表查询强制按 **`received_timestamp DESC`（从新到旧）** 排序。 |
| **5** | **机器学习全面学习转发习惯（转给谁、正文怎么改、带不带引文）** | **升级**：全面特征化学习：<br>① **哪里需要转发**：融合 `所属文件夹 + 发件人 + 我在收件人还是抄送人 + 主题/正文词组` 自动预测并标记待流转；<br>② **哪些带引文、哪些不带引文**：按 `(发件人 A, 目标收件人 F, 主题特征)` 记忆并预测你是习惯用**“改写为新邮件（不带引文）”**还是**“标准转发（带引文）”**；<br>③ **正文怎么改**：对比原邮件正文与你发出的正文，自动学习你的**专属称呼、正文主语/句式替换、标准转发时的顶部批注话术、以及结尾礼貌用语**。 |
| **6** | **按钮逻辑区分：【全部邮件】显示“需要流转”，【待流转】显示“无需流转”** | **完全采纳你的设计**：<br>• 在 **【全部邮件】** 中选中未标记流转的邮件时：隐藏“无需流转”按钮，显示 **`📌 标记为待流转（加入协同并训练AI）`** 按钮（点击后移入待流转列表、自动预拉取正文附件，并作为正样本训练机器学习）；<br>• 在 **【待流转邮件】** 中：显示 **`🚫 无需流转（移出待办并训练AI忽略）`** 按钮（点击后移出待流转列表，并作为负样本训练机器学习）。 |

---

## 二、 复制这段“六大问题终极修复 Prompt”发给你的 Agent

请直接把下面这段完整 Prompt 复制发给你的编码 Agent，让它一次性修复这 6 个问题：

```text
我实机测试发现了以下 6 个具体问题（附上了一张正文显示异常的实拍图：正文全变成了 `<!DOCTYPE html>...<title>网盘文件下载</title>.../coremail/bundle/X.a3565-1.css` 的网页源码），请一次性帮我全面修复 `core/mail_client.py`、`core/database.py`、`core/ml_learner.py`、`core/rewriter_engine.py`、`core/worker_threads.py`、`ui/main_window.py` 和 `main.py`：

---

### 修复 1：彻底解决“每篇邮件正文都显示 `<title>网盘文件下载</title>` 网页 HTML 源码”的 Bug（最核心！）
**原因定位**：
之前在 `fetch_single_email_detail` 中，方式 1 请求了 `/coremail/XT5/jsp/download.jsp`（或 `/coremail/s/eml`），在我的 Coremail XT (`v: 'eb2b3919'`) 服务器上该地址返回的是“网盘文件下载”的 Web 页面外壳（`<!DOCTYPE html><html><head>...<title>网盘文件下载</title>`）。因为没有校验返回内容是否为真正的 RFC822 EML，`_parse_raw_email` 把这个没有邮件头的 HTML 页面当成了 `text/plain` 纯文本正文存入了数据库，导致所有邮件正文都被这段代码污染了！

**请执行以下具体修复**：
1. **启动时自动清洗数据库中被污染的正文**：
   - 在 `core/database.py` 的 `init_db()` 中，立即执行一条修复 SQL：
     ```sql
     UPDATE emails
     SET body_text = '', body_html = '', is_body_loaded = 0
     WHERE body_text LIKE '%网盘文件下载%'
        OR body_html LIKE '%网盘文件下载%'
        OR body_text LIKE '%/coremail/bundle/%'
        OR body_html LIKE '%/coremail/bundle/%'
        OR body_text LIKE '<!DOCTYPE html%';
     ```
2. **重写 `core/mail_client.py` 中的 `_http_fetch_single_email_detail(self, mid: str)`**：
   - **严禁再请求 `/coremail/XT5/jsp/download.jsp`！**
   - 新增辅助函数 `_is_polluted_coremail_shell(text: str) -> bool`：凡是包含 `<title>网盘文件下载</title>`、`id=jSkin`、`/coremail/bundle/polyfill`、`var $, _ X =` 的内容，一律判定为 Coremail 网页外壳而非邮件正文，直接丢弃！
   - 按以下正确顺序获取 Coremail XT 邮件正文与附件：
     - **第 1 步（调用标准 JSON 读信接口 `mbox:readMessage`）**：
       请求 `POST {base_url}/coremail/s/json?sid={sid}&func=mbox:readMessage`，JSON Body 为：
       `{"mid": clean_mid, "mode": "html", "markRead": False, "returnImageInfo": True, "filterStylesheets": False}`。
       解析返回的 `var`：
       - 检查 `var.get("html", {}).get("content")`、`var.get("text", {}).get("content")`、`var.get("content")`；
       - 检查 `var.get("parts", [])` 或 `var.get("attachments", [])`：如果某个 part 的 `contentType` 是 `text/html` 或 `text/plain`：
         - 若该 part 直接带有非空的 `"content"` 字段，直接提取作为 `body_html` / `body_text`；
         - 若该 part 没有直接带 `"content"`，而是带有 `"id"` 或 `"partId"`（例如 `part_id = part.get("id") or part.get("partId")`），则请求 Coremail 官方流接口：
           `GET {base_url}/coremail/s?func=mbox:getMessageData&sid={sid}&mid={quote(clean_mid)}&part={part_id}&mode=html` 获取该 part 的真实正文内容！
     - **第 2 步（若第 1 步正文仍为空，调用 `mbox:getMessageData` 整信流接口）**：
       依次尝试：
       - `GET {base_url}/coremail/s?func=mbox:getMessageData&sid={sid}&mid={quote(clean_mid)}&mode=html`
       - `GET {base_url}/coremail/s?func=mbox:getMessageData&sid={sid}&mid={quote(clean_mid)}&mode=text`
       - `GET {base_url}/coremail/s?func=mbox:getMessageData&sid={sid}&mid={quote(clean_mid)}&mode=eml`
       （注意：只有当返回内容不命中 `_is_polluted_coremail_shell`，且在 `mode=eml` 下前 1024 字节必须包含 `From:` 或 `Subject:` 或 `MIME-Version:` 且不以 `<!DOCTYPE` 开头时，才交给 `_parse_raw_email` 解析！）
     - **第 3 步（HTML 正文净化与純文本提取）**：
       - 拿到 `body_html` 后，用 `BeautifulSoup` 移除所有的 `<script>`、`<style>`、`<link>`、`<meta>`、`<title>` 标签，提取 `<body>` 内部干净的富文本 HTML；并同步用 `soup.get_text("\n", strip=True)` 生成干净的 `body_text`！
       - 在 `ui/main_window.py` 右侧展示正文时：若 `body_html` 非空，直接调用 `setHtml(body_html)` 渲染富文本；若只有 `body_text` 但 `body_text` 内部本身是 HTML 标签（如包含 `<div`、`<p`、`<table`、`<br`），也必须用 `setHtml()` 渲染，**严禁把 HTML 标签源码用 `html.escape()` 转义成代码文字显示在屏幕上**！

---

### 修复 2：彻底解决“配置完第一次收信还是闪退”的问题
1. **主线程预热加载 `jieba` 与机器学习模型（防止 PyInstaller 下 `QThread` 子线程首次加载大词典栈溢出闪退）**：
   - 在 `main.py` 或 `MainWindow.__init__`（主线程）启动时，立即执行：
     ```python
     try:
         import jieba
         jieba.initialize()
     except Exception:
         pass
     ```
     并在主线程先完成 `LocalEmailLearner` 的初始化加载，避免在 `MailSyncWorker(QThread)` 子线程中首次冷启动初始化 `jieba` 词典。
2. **修复设置弹窗关闭时的线程冲突**：
   - 在 `ui/settings_dialog.py` 中，“测试连接”和“探测端口”若使用了后台线程，关闭弹窗（`accept` / `reject`）前必须等待线程安全结束。
   - 在 `ui/main_window.py` 的 `_open_settings()` 中，当 `dialog.exec() == QDialog.Accepted` 后，不要在弹窗关闭栈帧里直接同步启动 `start_mail_sync()`，而是使用 **`QTimer.singleShot(300, self.start_mail_sync)`** 延迟 300 毫秒待设置窗口完全销毁后再启动后台同步！

---

### 修复 3：邮件列表支持【按账号文件夹分类展示与筛选】，不再把所有邮件堆在一起
1. 在 `ui/main_window.py` 的中间邮件列表区顶部（搜索框下方或并排），新增一个醒目的 **【📁 文件夹筛选栏 (`QComboBox` 或胶囊切换栏)】**：
   - 默认第一项为 `📂 全部文件夹 (总数量)`；
   - 自动从数据库 `SELECT folder_name, COUNT(*) FROM emails GROUP BY folder_name` 动态加载账号下的所有文件夹及对应邮件数（例如：`📥 收件箱 (42)`、`📁 部门公文 (18)`、`📁 项目协调 (15)`...）；
   - 当用户切换文件夹下拉框时，列表立即只展示该文件夹下的邮件！
   - 在每封邮件列表项的卡片顶部，用醒目的彩色标签显示其所属文件夹 `[📁 {folder_name}]`。

---

### 修复 4：所有邮件严格按照【收信时间从新到旧】排序
1. **数据库新增标准化时间戳字段 `received_timestamp`**：
   - 在 `core/database.py` 的 `emails` 表中增加 `received_timestamp INTEGER DEFAULT 0` 字段（用 `ALTER TABLE` 自动升级旧表）。
2. **编写通用邮件时间解析函数 `parse_email_date_to_timestamp(raw_date: Any) -> Tuple[int, str]`**：
   - 兼容所有日期格式并统一转换为 `(unix_timestamp_seconds, "YYYY-MM-DD HH:MM")`：
     - 若 `raw_date` 是毫秒级时间戳（如 `1792390000000` 或 13 位数字字符串），除以 1000 转为秒级时间戳；
     - 若是秒级时间戳（10 位数字），直接转为 `int`；
     - 若是 `"2026-10-19 14:30:00"` 或 ISO 格式 `"2026-10-19T14:30:00"`，用 `datetime.fromisoformat` 解析；
     - 若是 RFC2822 英文邮件头格式（如 `"Mon, 19 Oct 2026 14:30:00 +0800"`），用 `email.utils.parsedate_to_datetime(raw_date)` 解析！
   - 在 `init_db()` 启动时，遍历数据库中 `received_timestamp == 0` 的存量邮件，自动根据 `date_str` 回填 `received_timestamp` 和格式化后的 `date_str`（`"YYYY-MM-DD HH:MM"`）！
3. **所有邮件查询强制按时间从新到旧排序**：
   - 在 `core/database.py` 的 `get_emails` / `list_emails` / `get_matched_emails` 中，SQL 排序子句全部统一改为：
     **`ORDER BY received_timestamp DESC, id DESC`**！确保无论邮件来自哪个文件夹，永远严格按照收信时间**从最新到最旧**排列！

---

### 修复 5：双向流转标记按钮逻辑改造（【全部邮件】只显示“需要流转”，【待流转】只显示“无需流转”）
请严格按照以下交互逻辑修改 `ui/main_window.py` 右侧底部操作栏与邮件列表右键菜单：
1. **当处于【全部邮件】视图（或当前选中的邮件 `is_matched == 0` / `status == 'ignored'`）时**：
   - **隐藏 `🚫 无需流转` 按钮**！
   - 显示 **`📌 标记为待流转（加入协同并训练AI）`** 按钮！
   - 点击 **`📌 标记为待流转`** 后的动作：
     1) 将数据库中该邮件的 `is_matched` 更新为 `1`，`status` 更新为 `'pending'`；
     2) 调用机器学习引擎 `learner.learn_from_user_action(email_data, action_label=1)` 进行正样本增量训练（让 AI 记住该发件人、该文件夹、该类主题/正文属于“需要流转”的邮件！）；
     3) 如果该邮件尚未加载完整正文与附件，立即启动后台线程拉取完整正文与附件；
     4) 刷新列表并在状态栏提示 `"✅ 已将该邮件标记为【待流转】，机器学习已记录此类邮件特征"`。
2. **当处于【待流转邮件】视图（或当前选中的邮件 `is_matched == 1` 且未忽略）时**：
   - **隐藏 `📌 标记为待流转` 按钮**！
   - 显示 **`🚫 无需流转（移出待办并训练AI）`** 按钮！
   - 点击 **`🚫 无需流转`** 后的动作：
     1) 将数据库中该邮件的 `is_matched` 更新为 `0`，`status` 更新为 `'ignored'`；
     2) 调用机器学习引擎 `learner.learn_from_user_action(email_data, action_label=0)` 进行负样本增量训练；
     3) 立即从当前【待流转邮件】列表中移除该邮件，并在状态栏提示 `"🚫 已移出待流转列表，机器学习已记住忽略此类邮件"`。
3. **邮件列表支持右键快捷菜单**：
   - 在邮件列表项上点击鼠标右键时，根据该邮件当前的 `is_matched` 状态，弹出菜单：`【📌 标记为待流转】`（当 `is_matched==0` 时）或 `【🚫 标记为无需流转】`（当 `is_matched==1` 时），方便在列表里快速批量标注训练 AI！

---

### 修复 6：强化机器学习引擎，全面学习转发习惯（哪里需要转发、带不带引文、正文怎么改）
请升级 `core/ml_learner.py` 和 `core/rewriter_engine.py`：
1. **全方位特征提取（学习“哪里需要转发”与“转给谁”）**：
   - 在 `_build_full_feature_text` 中，不仅提取主题和正文分词，还必须加入以下强特征 Token：
     - 所属文件夹特征：`f"__folder_{folder_name}__"`（权重 x2，因为特定文件夹的邮件往往固定需要或不需要流转！）
     - 发件人特征：`f"__from_{sender_email}__"`（权重 x3）
     - 我是否在主送收件人 `To` 中：`__me_in_to__` vs `__me_in_cc__`
     - 是否包含附件：`__has_attach__`
   - 当用户手动点击 `📌 标记为待流转` 或实际发送流转邮件时，在线分类器立即更新权重；新邮件同步或现有邮件重评估时，若 `need_action_prob >= 0.55`，自动标记 `is_matched = 1` 进入【待流转邮件】！
   - 新增一个 **“🤖 用最新 AI 模型重新扫描识别全部本地邮件”** 按钮（放在待流转/全部邮件顶部工具栏）：当你手动标记了几封“需要流转/无需流转”后，点一下该按钮，AI 会立即用刚学到的规律重新扫描本地所有邮件，自动把漏网的待流转邮件找出来标上！
2. **精准学习“哪些带引文（`standard_forward`），哪些不带引文（`rewrite_new`）”**：
   - 在 `LocalEmailLearner` 中，除了全局 `mode_clf` 分类器外，维护细粒度的习惯记忆矩阵：
     - `pair_mode_stats[(sender_email, target_f_email)] -> {"rewrite_new": count, "standard_forward": count}`
     - `sender_mode_stats[sender_email] -> {"rewrite_new": count, "standard_forward": count}`
     - `folder_mode_stats[folder_name] -> {"rewrite_new": count, "standard_forward": count}`
   - 预测某封邮件应该用“改写新建（不带引文）”还是“标准转发（带引文）”时，优先匹配 `(发件人A, 目标F)` 的历史习惯 -> 其次匹配 `发件人A` 的习惯 -> 其次匹配 `所属文件夹` 与 `mode_clf` 正文分类器，自动在发信确认弹窗中预选最符合你习惯的模式（带引文 vs 不带引文）！
3. **全面学习“正文怎么改”（称呼、正文句式替换、转发批注话术、结尾礼貌语）**：
   - 当用户在 `ComposeAndSendDialog` 中编辑正文并点击发送时：
     - 若模式为 **不带引文 (`rewrite_new`)**：
       1) 自动学习首行称呼习惯（更新对该收件人的 `preferred_salutation` 和 `use_salutation`）；
       2) 自动学习末尾最后一行礼貌结语（如用户把默认结语改成了 `"请抓紧落实反馈，谢谢！"`，自动保存针对该收件人或全局的习惯结语 `preferred_closing`）；
       3) 自动对比原邮件正文与用户修改后的正文，通过 `extract_fulltext_rewrite_diffs` 提取所有被用户修改的主语、人称、句式替换对，存入 `fulltext_rewrite_rules` 表！
     - 若模式为 **带引文转发 (`standard_forward`)**：
       1) 自动提取用户在 `------------------ 原始邮件 ------------------` 分隔线上方编写的**转发批注话术模板**（剥离称呼后，把发件人姓名泛化为 `{sender_name}`），记忆针对该收件人或该类邮件的常用转发批注（如 `"请阅处，{sender_name}发来的材料如下："`），下次对同类邮件选择带引文转发时自动填入！
```
