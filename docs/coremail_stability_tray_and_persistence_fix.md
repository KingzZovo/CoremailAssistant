# 五大核心问题根因诊断与终极修复方案：防闪退、解决收信与点邮件卡死、修复正文空白、最小化到托盘、跨版本数据继承

针对你刚刚实机测试反馈的 5 个问题，我逐一排查了底层调用链，找出了每个问题背后的精确代码原因，并为你准备好了**发给 Agent 的一键修复 Prompt**。

---

## 一、 为什么会出现这 5 个问题？（精确根因剖析）

| 你遇到的问题现象 | 底层代码真实原因 | 修复方案 |
| :--- | :--- | :--- |
| **1. 第一次同步直接闪退，第二次可以** | **Qt 线程引用覆盖崩溃（`QThread: Destroyed while thread is still running`）**：程序启动自动同步或连续点击同步时，`self.sync_worker = MailSyncWorker(...)` 直接覆盖了旧的还在运行的 `QThread` 变量，触发 Python 垃圾回收，Qt C++ 底层直接调用 `qFatal` 强行终止进程（无报错弹窗直接闪退）。 | 给所有 `QThread` 加运行锁与列表持有保护（运行中严禁覆盖销毁）；SQLite 开启 `WAL` 并发模式与 `timeout=30`。 |
| **2. 扫描收信容易卡死无响应，点邮件也卡死无响应** | **主线程同步网络阻塞 + 未保存回退端口导致每次白等 15 秒超时**：<br>① 连接时虽然从不通的 `993` (SSL) 自动回退到了 `143` 或 `HTTP`，但**没有把跑通的 `143` / `HTTP` 通道写回数据库保存**！导致每次收信、每次点邮件都要先去连不通的 `993` 端口白白卡死 15 秒等超时！<br>② 点击邮件拉取正文时，直接在 **UI 主线程**里调了网络请求，导致界面直接白屏转圈“未响应”。 | ① 一旦回退连通立即将有效端口/通道写入数据库，后续 0 等待直连；<br>② 点击邮件拉取正文必须放入后台异步线程 `EmailDetailWorker(QThread)`，绝不阻塞 UI。 |
| **3. 双击邮件卡死恢复后，右边还是看不到正文** | **文件夹名称编码与 UID 格式不匹配 + Coremail 正文字段兼容不全**：<br>① **IMAP 模式**：扫描时把文件夹名转成了中文 `"收件箱"`，并且把 UID 存成了 `"收件箱::123"`；等到点邮件拉正文时，把中文 `"收件箱"` 传给 `imap.select()`、把带前缀的 `"收件箱::123"` 传给 `imap.uid('fetch')`，服务端报错导致拉取正文失败返回空字符串！<br>② **HTTP 模式**：未完整兼容 `mbox:readMessage` / `mbox:getMessageData` 返回的嵌套正文结构（如 `var.html.content` / `var.parts`），且拉取完成后未刷新当前选中项的 HTML 视图。 | 拆分保存 `raw_folder`（原始文件夹编码）与纯数字 `raw_uid`；完整兼容 IMAP 与 HTTP 4 种正文读取接口，拉取后实时刷新右侧视图；若为空则显示具体报错原因。 |
| **4. 需要支持后台最小化到系统托盘** | 目前点击右上角最小化或关闭按钮时，没有拦截 `closeEvent` / `changeEvent` 隐藏窗口到系统托盘，或托盘图标因缺少外部 `.ico` 文件而未显示。 | 使用 Qt 内置标准高分屏图标初始化 `QSystemTrayIcon`，支持最小化/关闭时隐藏到托盘后台运行、双击托盘图标恢复窗口、右键菜单退出。 |
| **5. 每次升级新版都要重新填登录信息、重新收信、重新配置** | **数据目录被写死在程序运行目录 `./data` 下**：每次你下载新版本 `.exe` 解压到新文件夹运行，它都在新文件夹里新建了一个空白的 `data/assistant.db`！ | **将数据目录固定到 Windows 用户标准目录 `%LOCALAPPDATA%\CoremailAssistant\data\`**（即 `C:\Users\你的用户名\AppData\Local\CoremailAssistant\data`），启动时自动把旧目录的 `assistant.db` 迁移过去，并提供一键导入/导出备份功能，以后升级任何新版本都 100% 自动继承所有账号、配置与邮件！ |

---

## 二、 复制这段“五合一全方位修复 Prompt”发给你的 Agent

请直接把下面这段 Prompt 复制发给你的编码 Agent，它会一次性把**闪退、卡顿无响应、正文不显示、最小化到托盘、跨版本数据自动保留**全部修好：

```text
我实机测试现在可以收信了，但遇到了以下 5 个严重影响使用的问题，请一次性帮我彻底修复（修改 `config.py`、`core/database.py`、`core/mail_client.py`、`core/worker_threads.py`、`ui/main_window.py`、`ui/settings_dialog.py`）：

### 修复 1：跨版本升级数据永久保留与旧数据自动迁移（解决每次升级新版都要重新配账号、重新收信的问题）
1. 修改 `config.py`：
   - **严禁把 `DATA_DIR` 放在相对路径 `./data` 或 PyInstaller 临时目录中**！
   - 将 `DATA_DIR` 固定存储在当前 Windows 用户的本地应用数据目录下：
     ```python
     appdata_root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
     DATA_DIR = os.path.join(appdata_root, "CoremailAssistant", "data")
     ```
   - **自动迁移旧版数据**：在 `config.py` 初始化时，检查程序所在目录（`os.path.join(BASE_DIR, "data", "assistant.db")` 及当前工作目录 `os.path.abspath("data/assistant.db")`）是否存在旧版的 `assistant.db`：
     - 如果新的 `%LOCALAPPDATA%\CoremailAssistant\data\assistant.db` 还不存在，或者旧目录下的 `assistant.db` 修改时间更新/体积更大，自动将旧版 `data/` 下的 `assistant.db`、`ml_models.pkl` 和 `attachments/` 复制迁移到 `%LOCALAPPDATA%\CoremailAssistant\data\`！
2. 在 `ui/settings_dialog.py` 中新增【数据备份与恢复】区域：
   - 显示当前数据存储路径（并提供“📂 打开数据目录”按钮）；
   - 提供 **“💾 一键导出全部配置与数据备份 (.zip)”** 和 **“📥 导入恢复备份 (.zip)”** 按钮。

---

### 修复 2：彻底解决“第一次同步闪退”与“扫描收信/点邮件卡死无响应”
1. **消除 `QThread` 被覆盖导致的闪退 (`QThread: Destroyed while thread is still running`)**：
   - 在 `ui/main_window.py` 中维护 `self._active_workers = []` 列表；
   - 启动 `MailSyncWorker` 或任何 `QThread` 前，先检查 `if self.sync_worker and self.sync_worker.isRunning(): return`（若正在同步则直接忽略重复触发，绝不允许覆盖正在运行的 `QThread` 变量）！
   - 将新创建的 worker 加入 `self._active_workers`，并在其 `finished` 信号回调中安全移除。
2. **修复 SQLite 多线程并发锁**：
   - 在 `core/database.py` 的 `get_connection()` 中设置 `sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)`，并在初始化时执行 `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`。
3. **消除每次连接白等 15 秒超时的卡顿根源（持久化有效通道与端口）**：
   - 在 `core/mail_client.py` 中，将单次 socket/IMAP/HTTP 连接探测超时控制在 `4` 秒以内（不要用 15 秒阻塞！）。
   - **关键优化**：当 `_connect_imap` 从 `993` (SSL) 自动回退到 `143` (非SSL) 成功、或者自动切换到 `HTTP WebAPI` 通道成功时，**立即记录并缓存当前跑通的通道与端口（如 `self.imap_port = 143; self.imap_ssl = False`），并通过回调或 `db.save_setting` 写回数据库**！绝不允许下次同步或点邮件时又去连不通的 993 端口白等 15 秒！
   - 在 `MailSyncWorker` 同步过程中，复用同一个 `CoremailClient` 连接会话（IMAP 保持同一个 `conn` 连接，HTTP 复用同一个 `(base_url, sid)`），**严禁每拉一封邮件都重新登录一次服务器**！

---

### 修复 3：彻底解决“点击/双击邮件卡死，恢复后右边仍然看不到邮件正文”的问题
1. **严禁在 UI 主线程中同步拉取邮件正文（彻底消除点击邮件卡死无响应）**：
   - 在 `core/worker_threads.py` 中新增异步工作线程 `EmailBodyLoadWorker(QThread)`：
     - 接收 `(mail_client_config, db_manager, email_record)`；
     - 在后台线程调用 `client.fetch_single_email_detail(...)` 获取正文和附件，存入数据库后发射信号 `body_loaded = Signal(str, dict)`（携带 `uid` 和更新后的邮件字典）。
   - 在 `ui/main_window.py` 中，无论是**单击选中**还是**双击**邮件列表项：
     - 若该邮件已有正文（`body_text` 或 `body_html` 非空），立即在右侧渲染展示；
     - 若正文为空或 `is_body_loaded == 0`，右侧详情区立即显示 `"⏳ 正在后台加载邮件正文，请稍候..."`（界面完全不卡顿！），同时启动 `EmailBodyLoadWorker` 在后台拉取；拉取完成后收到 `body_loaded` 信号，立即调用右侧正文组件的 `setHtml()` 刷新显示！
2. **修复 `fetch_single_email_detail` 拉不到正文的 3 个核心 Bug（重点！）**：
   - **Bug A（IMAP 文件夹名与 UID 格式不匹配）**：
     - 在 `fetch_new_email_headers` 扫描 IMAP 文件夹时，除了保存供界面显示的中文名 `folder_name`（如 `"收件箱"`），必须在 `uid` 或字段中保留**原始 IMAP 文件夹标识 `raw_folder`**（如 `"INBOX"` 或 Modified UTF-7 原始名）和**纯数字邮件号 `raw_uid`**（例如将 `uid` 存为 `f"IMAP::{raw_folder}::{raw_uid}"`）。
     - 在 `fetch_single_email_detail` 中，如果 `uid` 以 `"IMAP::"` 开头，拆分出 `raw_folder` 和纯数字 `raw_uid`（若无前缀则从 `uid` 中用正则提取末尾纯数字 `re.findall(r'\d+', str(uid))[-1]`），先 `conn.select(f'"{raw_folder}"', readonly=True)`（若失败则回退 `conn.select("INBOX", readonly=True)`），再调用 `conn.uid("fetch", raw_uid, "(BODY.PEEK[])")`（若 `BODY.PEEK[]` 返回空则回退尝试 `(RFC822)`），用 `_parse_raw_email` 解析出完整的 `body_text` 和 `body_html`！
   - **Bug B（Coremail HTTP WebAPI 正文提取兼容性）**：
     - 在 HTTP 模式下读取单封邮件 `mid`（注意剥离可能被附加的文件夹前缀，保留原始 `mid`）时，依次尝试以下 3 种方式直到拿到非空正文：
       1) **方式 1**：`GET {base_url}/coremail/s/eml?sid={sid}&mid={quote(mid)}`（或 `/coremail/XT5/jsp/download.jsp?sid={sid}&mid={quote(mid)}`），若返回原始邮件字节流且包含邮件头，用 `_parse_raw_email` 解析；
       2) **方式 2**：`POST {base_url}/coremail/s/json?sid={sid}&func=mbox:readMessage`，Body: `{"mid": mid, "mode": "html", "markRead": False}`；
       3) **方式 3**：`POST {base_url}/coremail/s/json?sid={sid}&func=mbox:getMessageData`（或 `func=mbox:getMessageInfos`），Body: `{"mid": mid, "mode": "html"}`。
     - **递归提取返回 JSON 中的正文字段**：编写一个通用提取函数 `_extract_body_from_coremail_json(var_data)`，兼容以下所有 Coremail 版本返回结构：
       - `var_data.get("html", {}).get("content")` / `var_data.get("text", {}).get("content")`
       - `var_data.get("content")` / `var_data.get("body")` / `var_data.get("htmlBody")` / `var_data.get("textBody")`
       - `var_data.get("parts", [])` 列表中的 `content` 字段
       - 若以上均为空，但邮件列表缓存中有 `summary` 摘要，则用 `summary` 保底展示！
   - **Bug C（数据库更新与 UI 同步）**：
     - 拉取到 `body_text` / `body_html` 后，只有当正文确实非空时才将数据库中 `is_body_loaded` 置为 `1`；若拉取报错，在右侧详情区把具体的错误信息显示出来以便排查，不要显示空白页！

---

### 修复 4：完善最小化到系统托盘（后台常驻运行）
1. 在 `ui/main_window.py` 中：
   - 使用 `self.style().standardIcon(QStyle.SP_ComputerIcon)`（或用 `QPixmap` + `QPainter` 绘制一个蓝色信封图标）为 `QSystemTrayIcon` 设置默认图标，确保在任何打包环境下托盘图标都 100% 可见！
   - 顶部工具栏或左侧导航栏增加一个 **“🔽 最小化到托盘”** 按钮；
   - 重写 `changeEvent` 与 `closeEvent`：
     - 当用户点击窗口最小化按钮（`QEvent.WindowStateChange` 且 `isMinimized()`）或点击右上角关闭按钮（`closeEvent`）时，隐藏任务栏窗口 `self.hide()`，最小化到右下角系统托盘，并通过托盘弹出一次气泡提示 `"Coremail 协同助手已在后台托盘运行"`；
     - 支持**左键单击或双击托盘图标**立即恢复显示主窗口（`self.showNormal(); self.activateWindow()`）；
     - 托盘右键菜单包含：`【📂 打开主窗口】`、`【🔄 立即同步邮件】`、`【🚪 彻底退出程序】`（点击彻底退出时设置 `self._force_quit = True` 并调用 `QApplication.quit()`）。
```
