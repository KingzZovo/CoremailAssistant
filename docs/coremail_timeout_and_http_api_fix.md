# 为什么“服务器检测成功”，但测试连接和收信却报 `timeout`？根因诊断与真·Coremail WebAPI 修复方案

我刚刚专门去检查了你 GitHub 仓库里最新的 `core/mail_client.py` 和 `ui/settings_dialog.py` 源码，终于揪出了导致 **“检测提示成功，但测试连接和收信一直 `timeout`（超时）”** 的真正原因！

---

## 一、 两大真相：为什么检测成功却连接超时？

### 真相 1：仓库里的“服务器检测成功”是个“假成功（False Positive）”
在当前仓库的 `core/mail_client.py` 第 50~78 行 `probe_coremail_server_ports()` 中，你的 Agent 写了这样一段代码：

```python
if is_port_open(993):
    imap_port, imap_ssl = 993, True
elif is_port_open(143):
    imap_port, imap_ssl = 143, False
else:
    # 漏洞在这里：哪怕 993 和 143 端口全都被内网防火墙封死了（全超时），
    # 它依然强行赋值为 143，并且在下面固定返回 {"ok": True}！
    imap_port, imap_ssl = 143, False
```

也就是说：**只要你填的服务器 IP/域名能解析，哪怕这台服务器的 IMAP(143/993) 和 SMTP(25/465) 端口全都是关着的，它都会弹窗骗你说“🎉 论客服务器端口检测成功”**，并把不通的 `143` 和 `25` 填进设置里！

### 真相 2：你的内网封禁了 IMAP/SMTP 端口，而代码里的 `Coremail 协议` 模式底层还在硬连 IMAP/SMTP！
* 在绝大多数政企内网的 Coremail 部署中，出于安全策略，网管会**关闭或通过防火墙拦截标准的 IMAP（143/993）和 SMTP（25/465）端口**，只开放 **[Coremail 论客客户端](https://www.google.com/search?q=http%3A%2F%2Fwww.lunkr.cn%2F) 和网页版共用的 HTTP/HTTPS 端口（如 `80`、`443`、`8080`、`8443`）**。
* 但你仓库里的 `CoremailClient` 在选择 `Coremail 专用协议` 时，**并没有真正实现基于 HTTP/HTTPS 的 `/coremail/s/json` 接口**，它在 `test_connection()` 和 `fetch_new_emails()` 里依然在调用 Python 的 `imaplib.IMAP4(host, 143)` 去连被防火墙丢包的 143 端口，所以必然卡死 15 秒后报 **`timeout`（连接超时）**！

---

## 二、 终极解决方案：真正实现 Coremail HTTP/HTTPS 专用协议 (`/coremail/s/json`) + 真实端口扫描

要让软件在你的内网里像论客客户端一样秒连、秒收发，必须对 `core/mail_client.py` 做以下两项改造：

1. **改造 1：修复端口探测函数，如实扫描并汇报所有端口（严禁假成功）**
   * 同时探测 **Coremail HTTP/HTTPS 端口 (`443`, `80`, `8080`, `8443`)**、**IMAP 端口 (`993`, `143`)**、**POP3 端口 (`995`, `110`)** 和 **SMTP 端口 (`465`, `25`, `587`)**。
   * 清楚告诉用户当前服务器到底开了哪几个端口（例如：`检测到服务器仅开放 HTTP/HTTPS (80/443) 端口，已自动切换至 Coremail WebAPI 专用协议通道`）。
2. **改造 2：在 `core/mail_client.py` 中内置真正的 `Coremail WebAPI (/coremail/s/json)` 收发通道（外加 POP3 兜底）**
   * 当检测到 IMAP (`143`/`993`) 不通、或者用户处于 `Coremail 专用协议` 模式时，自动通过 `requests.Session`（设置 `trust_env=False` 绕过错误系统代理，`verify=False` 兼容内网自签名证书）直接调用 Coremail 服务端的标准 JSON 接口：
     * **登录认证**：`POST /coremail/s/json?func=user:login`（传入 `uid` 和 `password`，获取会话 `sid`）；
     * **拉取收件箱列表**：`POST /coremail/s/json?sid={sid}&func=mbox:listMessages`（获取收件箱最新邮件 `mid` 列表）；
     * **读取邮件全文、HTML 与原附件**：优先调用 `GET /coremail/s/eml?sid={sid}&mid={mid}` 直接拉取标准 RFC822 邮件原文交给 `_parse_raw_email` 解析，并同时支持 `POST /coremail/s/json?sid={sid}&func=mbox:readMessage` 解析正文与下载附件；
     * **发送新邮件/转发邮件**：调用 `POST /coremail/s/json?sid={sid}&func=mbox:compose` 直接通过 HTTP/HTTPS 发出富文本邮件与附件！

---

## 三、 复制这段“真·Coremail HTTP/WebAPI 协议修复 Prompt”发给你的 Agent

请直接把下面这段包含完整实现逻辑的 Prompt 复制发给你的编码 Agent，让它彻底重写 `core/mail_client.py` 的连接与收发逻辑：

```text
我实机测试发现：你之前写的 `probe_coremail_server_ports` 存在假阳性 Bug（当 993/143 和 465/25 端口全都不通时，else 分支依然返回了 143/25 且 `ok: True`），导致界面提示“服务器检测成功”，但实际内网防火墙封禁了 IMAP(143/993) 和 SMTP(25/465) 端口，所以点“测试连接”和“收信”时调 `imaplib`/`smtplib` 全部报 `timeout` 超时！

请立即修改 `core/mail_client.py` 和 `ui/settings_dialog.py`，完成以下真正的 Coremail 协议实现：

### 1. 修复 `probe_coremail_server_ports(raw_host: str)`（彻底杜绝假阳性，并探测 HTTP/HTTPS 与 POP3 端口）
- 如果用户输入中本身带有端口（如 `10.x.x.x:8080`），先提取出该自定义端口 `custom_port` 并优先探测。
- 依次用 `socket.create_connection((resolved_ip, port), timeout=1.5)` 真实探测以下四组端口：
  1) **Coremail HTTP/HTTPS 专用协议端口**：`[custom_port, 443, 80, 8080, 8443]`（并通过 `requests.get(f"{scheme}://{clean_host}:{port}/coremail/", timeout=2.5, verify=False)` 验证是否存在 Coremail Web 服务）
  2) **IMAP 端口**：`[993, 143]`
  3) **POP3 端口**：`[995, 110]`
  4) **SMTP 端口**：`[465, 25, 587]`
- **严禁在端口不通时赋默认值冒充成功**！将真实开放的端口列表记录在返回字典中：
  - 若 IMAP 开放，记录 `open_imap_port`；若未开放，设为 `None`！
  - 若 HTTP/HTTPS (80/443/8080/8443) 开放，记录 `http_base_url`（如 `http://10.x.x.x:80` 或 `https://10.x.x.x:443`）！
  - 若所有端口（HTTP/HTTPS/IMAP/POP3/SMTP）全都不通，返回 `{"ok": False, "msg": "服务器 IP 可解析，但 80/443/143/993/25/465 端口均连接超时，请检查论客客户端【帐号管理】中的真实服务器 IP 和端口号"}`。
  - 在成功返回的 `msg` 中明确列出实际开放的端口（例如：`已探测到开放端口：HTTP/Coremail协议(80/443)` 或 `IMAP(143), SMTP(25)`）。

### 2. 在 `CoremailClient` 中实现真正的 Coremail HTTP/HTTPS WebAPI (`/coremail/s/json`) 收发引擎
请使用 `urllib3.disable_warnings()` 和 `requests.Session()`（必须设置 `session.trust_env = False` 忽略可能损坏的 Windows 系统代理，且 `verify=False` 忽略内网自签名 SSL 证书）实现以下方法，当 `protocol_mode == "coremail"` 且 IMAP 端口不通（或优先使用 HTTP API）时自动走 HTTP/HTTPS 通道：

1) **`_http_login(self) -> Tuple[str, str]`**：
   - 自动尝试候选 `base_url`（优先尝试用户填写的协议/端口，其次依次尝试 `https://{host}`、`http://{host}`、`http://{host}:8080`）。
   - 向 `{base_url}/coremail/s/json?func=user:login` 发送 POST 请求：
     - Header: `{"Content-Type": "application/json; charset=UTF-8", "User-Agent": "L-CMClient/5.0"}`
     - JSON Body: `{"uid": self.email_account, "password": self.email_password, "supportVerifyCode": False}`
   - 同时兼容表单回退登录：若 `/coremail/s/json?func=user:login` 返回需要完整域名或特定格式，也尝试 `uid` 为完整邮箱及 `@` 前缀用户名两种格式。
   - 若返回 JSON 中 `res.get("code") == "S_OK"` 且包含 `var.sid`，保存并返回 `(base_url, sid)`！若返回 `FA_UNAUTHORIZED` 或密码错误，直接抛出明确的账号或密码错误异常（不再盲目等待超时）。

2) **`_http_fetch_new_emails(self, existing_uids: set, max_fetch: int = 30) -> List[Dict[str, Any]]`**：
   - 先调用 `self._http_login()` 获取 `(base_url, sid)`。
   - 调用 `POST {base_url}/coremail/s/json?sid={sid}&func=mbox:listMessages`，Body 为：
     `{"fid": 1, "start": 0, "limit": max_fetch, "order": "receivedDate", "desc": True, "returnTotal": True}`
   - 遍历返回的邮件列表 `var`（每项含 `id` 作为 `mid`）：
     - 若 `str(mid)` 已在 `existing_uids` 中则跳过；
     - **方式 A（优先下载原始 EML 复用完整解析器）**：请求 `GET {base_url}/coremail/s/eml?sid={sid}&mid={urllib.parse.quote(str(mid))}`，若状态码为 200 且返回字节流非空，直接调用现有的 `self._parse_raw_email(str(mid), resp.content)`，即可 100% 完整解析主题、发件人、收件人、抄送人、富文本 HTML、内联图片与所有附件！
     - **方式 B（JSON 详情回退）**：若 `/coremail/s/eml` 不可用，调用 `POST {base_url}/coremail/s/json?sid={sid}&func=mbox:readMessage`，Body 为 `{"mid": mid, "mode": "html", "markRead": False}`，从返回的 `var` 中提取 `subject`、`from`、`to`、`cc`、`sentDate`、`html`/`text` 正文，并通过 `{base_url}/coremail/s/attach?sid={sid}&mid={mid}&aid={att_id}` 下载附件存入 `data/attachments/{safe_mid}/`。

3) **`_http_send_email(self, to_addrs, cc_addrs, subject, html_body, plain_body, attachment_paths, save_to_sent=True)`**：
   - 先调用 `self._http_login()` 获取 `(base_url, sid)`。
   - 若有附件或内联图片，先通过 `POST {base_url}/coremail/s/upload?sid={sid}`（或 `func=upload:prepare` + 二进制上传）上传获取附件 ID 列表。
   - 调用 `POST {base_url}/coremail/s/json?sid={sid}&func=mbox:compose`，Body 为：
     ```json
     {
       "attrs": {
         "account": self.email_account,
         "to": to_addrs,
         "cc": cc_addrs,
         "subject": subject,
         "isHtml": True,
         "content": html_body or plain_body,
         "saveSent": save_to_sent,
         "attachments": uploaded_attachments
       },
       "action": "deliver",
       "returnInfo": True
     }
     ```
   - 检查返回 `code == "S_OK"`，若失败抛出具体原因。

4) **智能多通道调度（`test_connection`、`fetch_new_emails`、`send_email`）**：
   - 在 `test_connection()` 中：
     - 先跑一次快速端口探测（耗时 < 2秒，不要盲目用 15 秒 timeout 去连没开的端口！）；
     - 如果检测到 `80`/`443`/`8080` 等 HTTP(S) 端口开放，优先用 `_http_login()` 测试 Coremail WebAPI 登录；
     - 如果检测到 `993`/`143` 开放，才去连 IMAP；如果只开了 `995`/`110`，支持用 `poplib` 测试 POP3 登录；
     - 把实际走通的通道（例如 `Coremail HTTP/HTTPS WebAPI 通道连接验证成功` 或 `IMAP/SMTP 通道连接验证成功`）清晰展示给用户！

### 3. 编写单元测试验证
- 更新 `tests/` 下的测试脚本，模拟当 143/993/25/465 端口全部超时关闭、仅 80/443 开放时，`probe_coremail_server_ports` 能准确识别 HTTP 通道，且 `CoremailClient` 能通过 `/coremail/s/json` 完成 `test_connection`、`fetch_new_emails` 和 `send_email`。
```
