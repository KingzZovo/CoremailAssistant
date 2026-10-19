# 为什么连接成功却“拉取 0 封新邮件”？多文件夹扫描与“仅协调邮件预拉正文附件”升级方案

恭喜你已经打通了内网服务器连接！针对你提出的两个核心问题：
1. **为什么点击立即同步显示“拉取 0 封新邮件”（且你有多个文件夹）？**
2. **能不能做到“不需要所有邮件都拉取正文与附件，只有协调邮件自动拉取正文与附件，其他普通邮件按需拉取”？**

下面为你详细解答原因，并提供直接发给 Agent 的一键升级 Prompt。

---

## 一、 解答你的疑问：为什么会显示“拉取 0 封新邮件”？

### 1. 目前的统计逻辑是算“全部新邮件”还是“仅协调邮件”？
在 `core/worker_threads.py` 的 `MailSyncWorker` 中，状态栏提示的“拉取 X 封新邮件”统计的是 **`fetch_new_emails()` 从服务器拿回来的新邮件总数**（无论是否需要协调）。
因此显示 **“拉取 0 封新邮件”**，说明代码在调用收信接口时**没有从服务器读到邮件列表**，主要有以下 3 个原因：

| 原因排序 | 具体问题定位 | 为什么会导致拉取为 0 |
| :--- | :--- | :--- |
| **原因 1（最关键）** | **代码写死了只查默认收件箱（`fid=1` 或 `INBOX`），完全没查你的其他文件夹** | 你提到你除了收件箱还有**其他文件夹**。在 [Coremail 论客客户端](https://www.google.com/search?q=http%3A%2F%2Fwww.lunkr.cn%2F)中，如果配置了收信分类规则（过滤器），新邮件一进来就会被自动移入自定义文件夹（在 Coremail 中自定义文件夹的 `fid` 不是 `1`）。只查 `fid=1` 会漏掉所有其他文件夹里的邮件！ |
| **原因 2** | **Coremail `mbox:listMessages` 返回 JSON 的结构差异被忽略** | 不同版本的 Coremail 服务端返回 `mbox:listMessages` 时，有的版本邮件列表直接在 `res["var"]`（List），而有的版本（如 XT5/XT6）包裹在字典 `res["var"]["messages"]` 或 `res["var"]["list"]` 中。如果代码只判断了 `isinstance(var, list)`，遇到字典就会当成 0 封处理！ |
| **原因 3** | **`_http_login` 的“网页回退登录”返回了虚拟 `sid`，或异常被 `try...except` 静默吞掉** | 如果 `_http_login` 在 JSON 登录未命中时走到了网页 GET 200 回退（没有拿到真正的 Coremail 会话 `sid`），测试连接虽然显示成功，但调用 `listMessages` 时服务端会返回 `FA_INVALID_SESSION`，而代码在 `except Exception:` 中直接 `return []`，导致界面静默显示“0 封新邮件”而不报错。 |

---

## 二、 你的架构建议非常精准：两阶段“信头全扫 + 正文附件按需拉取（Lazy-Load）”

你的想法完全符合高性能邮件客户端的设计标准：**绝不应该把所有普通邮件的正文和几十兆的附件一股脑全下到本地！**

我们直接将收信与存储引擎升级为 **“两阶段按需拉取（Header-First & Lazy-Load）”架构**：

```text
【第 1 步：全文件夹扫描信头（极速，毫秒级）】
调用 func=mbox:getAllFolders（或 IMAP LIST）获取所有收件类文件夹（收件箱 + 你的所有自定义文件夹，排除已删除/垃圾箱/草稿/已发送）
       ↓
批量拉取各文件夹最新邮件的【轻量信头元数据】（仅含：UID/MID、所属文件夹名、主题、发件人、收件人、抄送人、时间、50字摘要，不下载完整正文和附件！）
       ↓
【第 2 步：规则 + 机器学习快速分流】
 ├── 命中【需要协调流转 (is_matched = 1)】 ──► 立即自动拉取该邮件的【完整 HTML/纯文本正文 + 下载原邮件附件】缓存到本地，点开即可秒速改写/转发！
 └── 未命中【普通邮件 (is_matched = 0)】   ──► 仅将轻量信头存入本地数据库（标记 body_loaded = 0），跳过正文与附件下载！
                                                └── 当你在界面上点击查看某封普通邮件（或对它点改写/转发）时，才实时按需拉取该封邮件的正文与附件（Lazy-Load）！
```

---

## 三、 复制这段“多文件夹扫描 + 按需拉取正文附件 Prompt”发给你的 Agent

请直接复制下面这段 Prompt 发给你的编码 Agent，它会一次性解决 **“拉取 0 封邮件”**、**“支持所有自定义文件夹”** 以及 **“仅协调邮件预拉取正文附件，普通邮件按需加载”** 三大需求：

```text
我现在测试连接成功了，但点击“立即同步邮件”显示“拉取 0 封新邮件”。我有多个自定义邮件文件夹（不只是默认收件箱），而且我不希望把所有普通邮件的正文和附件都下载到本地。
请帮我对 `core/mail_client.py`、`core/database.py`、`core/worker_threads.py` 和 `ui/main_window.py` 进行以下升级改造：

### 任务一：排查并修复“拉取 0 封新邮件”的 3 个根因，并支持【全文件夹（收件箱 + 自定义文件夹）扫描】

1. **严禁 `_http_login` 使用虚假的网页 200 回退冒充登录成功**：
   - 在 `core/mail_client.py` 的 `_http_login()` 中，必须真正拿到 Coremail 服务端签发的有效 `sid`（通过 `/coremail/s/json?func=user:login` 返回的 `var.sid`，或者登录表单重定向 URL / Cookie `Coremail.sid` 中提取出的真实 `sid`）。
   - 如果没有拿到真实 `sid`，或者如果走的是 IMAP/POP3 通道，必须用实际协议完成登录认证，绝不能仅凭 `GET /coremail` 返回 HTTP 200 就生成一个假 `sid`！
   - **禁止静默吞掉收信异常**：在 `fetch_new_emails` / `_http_fetch_new_emails` 中，如果请求失败或返回错误码（如 `FA_INVALID_SESSION`），必须抛出异常通过 `MailSyncWorker.sync_finished` 显示在界面状态栏上，绝不能静默 `except: return []` 伪装成“0 封新邮件”！

2. **自动获取并扫描用户的所有收件文件夹（收件箱 + 所有自定义文件夹）**：
   - **HTTP WebAPI 模式 (`/coremail/s/json`)**：
     - 先调用 `POST {base_url}/coremail/s/json?sid={sid}&func=mbox:getAllFolders`（Body 为 `{}`），从返回的 `var` 列表中提取所有文件夹：
     - 自动排除系统非收信文件夹：排除 `id` 在 `(2, 3, 4, 5)` 中（2=草稿箱, 3=已发送, 4=已删除, 5=垃圾邮件）或名称为 `草稿`、`已发送`、`已删除`、`垃圾`、`Sent`、`Drafts`、`Trash`、`Spam`、`Junk` 的文件夹；**保留 `fid=1`（收件箱）以及用户创建的所有其他自定义文件夹**！
     - 若 `getAllFolders` 未返回列表，则至少保底扫描 `fid=1`。
   - **IMAP 模式**：
     - 调用 `conn.list()` 获取所有文件夹名称（支持解码 IMAP Modified UTF-7 中文文件夹名，如 `&V4NXPpCuTvY-`），排除 `Sent`、`Drafts`、`Trash`、`Junk`、`Spam`、`已发送`、`草稿`、`已删除`、`垃圾`，扫描 `INBOX` 及所有用户自定义文件夹！
   - **兼容不同 Coremail 版本的 `mbox:listMessages` 返回格式**：
     - 对每个文件夹调用 `func=mbox:listMessages`（Body: `{"fid": folder_id, "start": 0, "limit": max_fetch, "order": "receivedDate", "desc": True, "returnTotal": True}`）时：
     - 兼容返回 JSON 中 `var` 直接是 `list` 的情况，**同时也必须兼容 `var` 是 `dict`（邮件列表在 `var.get("messages")`、`var.get("list")` 或 `var.get("items")` 中）的情况**！
     - 为每封邮件记录所属文件夹名称 `folder_name`（如 `"收件箱"` 或 `"项目协调"`）。

---

### 任务二：实现“两阶段按需拉取（Header-First & Lazy-Load）”——仅协调邮件自动拉取正文与附件，其他邮件按需拉取

1. **数据库层 (`core/database.py`) 升级**：
   - 在 `emails` 表中新增两个字段（若旧表不存在则用 `ALTER TABLE emails ADD COLUMN ...` 自动平滑升级）：
     - `folder_name TEXT DEFAULT '收件箱'`（记录邮件来自哪个文件夹）
     - `is_body_loaded INTEGER DEFAULT 1`（`1` 表示已拉取完整正文与附件，`0` 表示仅拉取了信头元数据、尚未下载正文与附件）
   - 新增方法 `update_email_body_and_attachments(self, uid: str, body_text: str, body_html: str, attachments_json: str)`：当按需拉取某封邮件的正文和附件后，更新该邮件记录并将 `is_body_loaded` 设为 `1`。

2. **客户端层 (`core/mail_client.py`) 拆分“轻量拉取信头”与“按需拉取单封正文+附件”**：
   - 新增/改造 `fetch_new_email_headers(self, existing_uids: set, max_fetch_per_folder: int = 25) -> List[Dict[str, Any]]`：
     - 遍历收件箱与所有自定义文件夹，**仅拉取新邮件的信头与简短摘要**（在 HTTP API 中直接从 `mbox:listMessages` 返回的列表项里提取 `id`, `subject`, `from`, `to`, `cc`, `receivedDate`, `summary`；在 IMAP 中使用 `BODY.PEEK[HEADER]` 拉取信头，**绝不在此阶段下载邮件正文与附件**！）。
     - 返回轻量邮件字典列表（此时 `is_body_loaded = 0`）。
   - 新增 `fetch_single_email_detail(self, uid: str, folder_name: str = "INBOX") -> Dict[str, Any]`：
     - 根据 `uid`（HTTP 的 `mid` 或 IMAP 的 `folder::uid`）专门拉取**这一封邮件**的完整 `body_text`、`body_html` 并将附件下载到 `data/attachments/{safe_uid}/`，返回 `{"body_text": ..., "body_html": ..., "attachments": [...], "is_body_loaded": 1}`。

3. **后台同步线程 (`core/worker_threads.py` 中 `MailSyncWorker`) 升级**：
   - 第一步：调用 `client.fetch_new_email_headers(...)` 快速拿回所有文件夹的新邮件信头列表。
   - 第二步：对每封新邮件，先用 `subject`、`sender_email`、`folder_name` 和 `summary` 运行关键词规则匹配与 `LocalEmailLearner.predict_email` 初筛：
     - **如果判定为【需要协调流转 (`is_matched == 1`)】**：立即在后台调用 `client.fetch_single_email_detail(uid, folder_name)` 把它的完整正文（HTML/纯文本）和附件下载下来，設 `is_body_loaded = 1`，方便用户点开直接改写或转发！
     - **如果判定为【普通邮件 (`is_matched == 0`)】**：**不拉取正文和附件**（`is_body_loaded = 0`），直接把信头存入本地数据库！大幅提升同步速度并节省磁盘空间。
   - 状态栏完成提示格式优化为：`f"同步完成：共扫描 {folder_count} 个文件夹，新增 {len(new_emails)} 封邮件（其中 {matched_count} 封需协调邮件已预载正文与附件）"`。

4. **UI 层 (`ui/main_window.py` & `ui/compose_send_dialog.py`) 点击时按需加载（Lazy-Load）**：
   - 当用户在主窗口列表中点击选中某封邮件（或点击“改写为新邮件”/“标准转发”）时，检查 `email_data.get("is_body_loaded", 1) == 0`：
   - 若为 `0`，立即在状态栏/详情区显示 `"⏳ 正在按需加载该邮件正文与附件..."`，调用 `client.fetch_single_email_detail(...)` 获取正文与附件，调用 `db.update_email_body_and_attachments(...)` 缓存入库后刷新详情展示！
   - 在邮件列表卡片上显示该邮件所属的文件夹标签（如 `[📁 收件箱]` 或 `[📁 项目组]`）。
```
