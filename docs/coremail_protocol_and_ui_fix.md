# 实机测试问题诊断与修复方案：`errno 11001` 连接报错、Coremail 专用协议适配与界面“F/A”文案清理

针对你实机测试遇到的两个问题，这里先给出**立即可用的排查解决方法**，随后提供**完整的代码升级补丁与一键修复 Prompt**（让软件像论客客户端一样原生支持“Coremail 协议”单地址登录，并彻底清除界面上所有举例用的字母 `F`、`A`）。

---

## 一、 为什么会报 `errno 11001`？怎么在论客客户端查真实服务器地址？

### 1. `errno 11001` 的真实含义
在 Windows 网络编程中，`[Errno 11001] getaddrinfo failed` 代表 **“主机名/域名无法解析或格式不合法”**。结合你看到论客客户端显示 **“协议：Coremail”**，通常由以下 3 个原因之一引起：

| 常见原因 | 错误示例 | 正确填法（立即可试） |
| :--- | :--- | :--- |
| **原因 1：服务器地址带了 `http://`、端口号或斜杠路径** | 在论客的 `coremail` 协议下，服务器地址常显示为 `http://10.x.x.x:8080` 或 `https://mail.xx.cn/`。如果直接带 `http://` 或 `:端口` 填进 IMAP/SMTP 框，Python `socket` 会直接报 `11001` | **只保留纯 IP 或纯域名**（例如只填 `10.x.x.x` 或 `mail.xx.cn`，去掉 `http://`、去掉冒号后的端口和斜杠） |
| **原因 2：在内网填了外网习惯的 `imap.xx` / `smtp.xx` 域名** | 你的邮箱是 `name@corp.cn`，如果在设置里填了 `imap.corp.cn`，但内网 DNS 并没有配 `imap.` 前缀记录，就会报 `11001` | **IMAP 服务器和 SMTP 服务器都填跟论客客户端完全一致的那个 IP 或主域名**（内网 Coremail 的 Web、Coremail 协议、IMAP、SMTP 全在同一台机器上） |
| **原因 3：内网 Coremail 没开 SSL，用了默认的 993/465 端口** | 纯内网通常不配 SSL 证书，只开明文端口 | 将 **IMAP 端口改为 `143`（取消勾选 SSL）**，**SMTP 端口改为 `25`（取消勾选 SSL）** |

### 2. 如何在【Coremail 论客客户端】里看真实的服务器 IP / 域名？
1. 打开你的 [Coremail 论客客户端](https://www.google.com/search?q=http%3A%2F%2Fwww.lunkr.cn%2F)，点击左下角或右上角的 **【设置（齿轮图标）】 -> 【帐号管理】**。
2. 选中你的邮箱账号，查看右侧的 **【服务器设置】**：
   * 你会看到 **协议类型：`Coremail`**，下面有一行 **【服务器】**（或者【服务器地址】），比如写着 `192.168.10.25` 或 `mail.xxxx.local:80`。
   * **把这个地址里的纯 IP 或纯域名复制出来**，同时填进我们软件设置的 **IMAP 服务器** 和 **SMTP 服务器** 两栏中，并将端口设为 `143`（IMAP，关闭SSL）和 `25`（SMTP，关闭SSL）即可连通！

---

## 二、 代码级永久升级方案（让软件直接支持 Coremail 协议 + 清除界面上的“F/A”）

为了让你不用折腾端口，同时把界面上那几个把举例字母 `"F"`、`"A"` 当成固定文字的按钮彻底改掉，我们直接对软件做三项升级：

1. **升级 1：在设置界面直接支持切换【Coremail 专用协议】与【IMAP/SMTP 协议】**
   * 当选择 **`Coremail 专用协议（同论客客户端）`** 时，设置界面**只显示一个“服务器地址”输入框**（和论客客户端完全一样！即使你粘贴了 `http://10.1.1.5:8080/`，代码也会自动解析主机与端口）。
   * 底层会自动先尝试 Coremail WebAPI（`/coremail/s/json`），并自动探测同一台服务器上的 `143`/`993`/`25`/`465` 端口完成收发！
2. **升级 2：增加“🔍 自动探测服务器端口”与主机名清洗（彻底消灭 `errno 11001`）**
   * 自动剥离用户输入的 `http://`、`https://`、路径 `/coremail`、多余空格与尾随端口号；若 DNS 解析失败，直接给出中文提示“无法解析域名 xxx，请改填内网 IP 地址”。
3. **升级 3：彻底清除界面上所有 `"F"`、`"A"`、`"B/C/D"` 举例字母**
   * 将主窗口和发信确认弹窗里的：
     * `"✨ 改写为新邮件发给 F"` 改为 **`"✨ 改写为新邮件发送"`**（若规则或机器学习已匹配出推荐收件人如“张工”，则动态显示为 **`"✨ 改写为新邮件（推荐：张工）"`**）；
     * `"↪️ 标准转发给 F"` 改为 **`"↪️ 标准带引文转发"`**；
     * `"收件人 F"` 改为 **`"收件人"`**；
     * `"抄送原发件人 A"` 改为 **`"抄送原发件人"`**（或动态显示原发件人姓名，如 **`"抄送原发件人（李明）"`**）；
     * `"对照查看 A 的原邮件原文"` 改为 **`"对照查看原邮件内容"`**。

---

## 三、 复制这段“一键修复 Prompt”发给你的 Agent

请直接复制下面这段 Prompt 发给你的编码 Agent，它会一次性修好 `errno 11001`、加上 `Coremail 专用协议` 模式，并把所有界面上的 `"F"` 和 `"A"` 全部替换成专业自然的中文：

```text
请帮我对仓库进行以下两项重要修复与体验升级（请直接修改对应文件并保持所有现有功能完整）：

### 任务一：解决 `errno 11001` 连接报错，并新增“Coremail 专用协议（单服务器地址）”模式

1. 修改 `core/mail_client.py`：
   - 新增静态辅助函数 ` normalize_host_and_port(raw_host: str, default_port: int) -> Tuple[str, int, str]`：
     - 自动去除首尾空格；
     - 如果用户输入了 `http://10.1.1.5:8080/coremail` 或 `10.1.1.5:143` 这种带协议头、路径或冒号端口的字符串，使用 `urllib.parse` 自动提取纯净的 `hostname/IP`（绝不能把 `http://`、`:端口` 或 `/` 传给 `imaplib`/`smtplib`/`socket`，否则 Windows 必报 `errno 11001`）！
   - 新增静态方法 `auto_detect_server(raw_host: str) -> Dict[str, Any]`：
     - 先用 `socket.gethostbyname(clean_host)` 检查域名/IP 是否可解析；若报 `socket.gaierror (errno 11001)`，返回清晰中文提示：`"无法解析服务器地址 '{clean_host}' (Errno 11001)，请检查是否拼写错误，或在纯内网中直接填写邮件服务器的 IP 地址"`。
     - 自动使用 `socket.create_connection((clean_host, port), timeout=2.5)` 探测该服务器的常用端口：
       - IMAP 优先探测 `993` (SSL) 和 `143` (非SSL，内网最常见)；
       - SMTP 优先探测 `465` (SSL) 和 `25` (非SSL，内网最常见)；
       - Web/Coremail 专用协议探测 `443` (HTTPS) 和 `80` / `8080` (HTTP)；
     - 返回探测成功的推荐配置字典：`{"ok": True, "host": clean_host, "imap_port": ..., "imap_ssl": ..., "smtp_port": ..., "smtp_ssl": ...}`。
   - 在 `CoremailClient.__init__` 中：
     - 支持 `protocol_mode` 配置项（`"coremail"` 或 `"imap_smtp"`，默认 `"coremail"`）。
     - 当 `protocol_mode == "coremail"` 时，允许用户只填一个 `coremail_server` 地址（自动同步应用到 `imap_host` 和 `smtp_host`），如果当前配置的 993/465 连不通，自动回退尝试同一台服务器的 `143` (非SSL IMAP) 和 `25` (非SSL SMTP) 端口，还会支持通过 Coremail WebAPI (`/coremail/s/json?func=user:login`) 校验登录！

2. 修改 `ui/settings_dialog.py` 和 `config.py`：
   - 在邮箱配置顶部增加 **【协议类型】下拉框**：
     - 选项 1：**`Coremail 专用协议（同论客客户端，仅需填一个服务器地址）`**
     - 选项 2：**`IMAP / SMTP 标准协议（手动分别指定端口）`**
   - 当选择 `Coremail 专用协议` 时，合并显示一个 **“服务器地址（IP 或域名，与论客客户端一致）”** 输入框，并在旁边提供 **“🔍 自动检测端口与连接”** 按钮（点击后自动清洗地址、探测内网开启的是 143/25 还是 993/465，并自动填充保存）。

---

### 任务二：全局清理界面上把举例字母“F”、“A”、“B/C/D”当成固定文案的问题

请全局搜索 `ui/main_window.py`、`ui/compose_send_dialog.py`、`ui/rule_contact_dialog.py`、`ui/settings_dialog.py`，将所有带示例字母 `F`、`A`、`B/C/D` 的硬编码 UI 文本全部替换为标准专业的邮件客户端表述（或动态显示真实联系人姓名）：

1. `ui/main_window.py`：
   - 将 `"✨ 改写为新邮件发给 F..."` 按钮文本改为 **`"✨ 改写为新邮件发送"`**；当选中邮件且存在推荐收件人时，动态更新按钮文字为 **`f"✨ 改写为新邮件（推荐发给：{推荐人姓名或邮箱}）"`**。
   - 将 `"↪️ 标准转发给 F..."` 按钮文本改为 **`"↪️ 标准带引文转发"`**。
   - 将邮件列表或详情中任何写有 `"发件人 A"`、`"抄送 B, C, D"`、`"目标 F"` 的静态标签，全部改为自然的 **`"发件人"`**、**`"抄送"`**、**`"推荐收件人"`**。

2. `ui/compose_send_dialog.py`：
   - 顶部模式切换按钮：改为 **`"✨ 改写为新邮件（脱壳改称呼与主语）"`** 和 **`"↪️ 标准带引文转发"`**（去掉字母 `F`）。
   - `"收件人 F"` 标签改为 **`"收件人："`**；下方常用联系人区域标题改为 **`"常用收件人快捷勾选（点击自动联动称呼与抄送栏）："`**。
   - `"抄送人 A, B, C, D"` 标签改为 **`"抄送人："`**。
   - 右侧复选框 `"抄送原发件人 A"` 改为动态显示真实发件人姓名：**`f"抄送原发件人（{sender_name or sender_email}）"`**（若无则显示 `"抄送原发件人"`）。
   - `"当前对 F 的称呼"` 改为 **`"开头称呼："`**。
   - `"对照查看 A 的原邮件原文"` 改为 **`"对照查看原邮件内容"`**。

3. `ui/rule_contact_dialog.py`：
   - 将表格列头和表单提示中的 `"默认收件人 F"`、`"常驻候选 F"`、`"特定发件人 A"`、`"特定收件人 F"` 全部改为 **`"默认转发/流转收件人"`**、**`"设为常用快捷收件人"`**、**`"限定原发件人（可选）"`**、**`"限定目标收件人（可选）"`**。
```

---

## 四、 附：`core/mail_client.py` 清洗地址与自动探测内网 Coremail 端口核心代码

如果你想了解底层是如何解决 `errno 11001` 并兼容内网 Coremail 服务器的，下面是核心实现逻辑：

```python
import socket
from urllib.parse import urlparse
from typing import Tuple, Dict, Any


def normalize_host_and_port(raw_host: str, default_port: int) -> Tuple[str, int]:
    """
    清洗用户在设置中填写的服务器地址，防止因包含 http://、端口号或路径导致 Windows 报 Errno 11001。
    例如输入 'http://192.168.1.50:8080/coremail/' -> 返回 ('192.168.1.50', 8080)
    输入 'mail.corp.local' -> 返回 ('mail.corp.local', default_port)
    """
    if not raw_host:
        return "", default_port
    s = raw_host.strip()
    if "://" not in s:
        s = "http://" + s
    parsed = urlparse(s)
    clean_host = (parsed.hostname or "").strip()
    port = parsed.port or default_port
    return clean_host, port


def probe_coremail_server_ports(raw_host: str) -> Dict[str, Any]:
    """
    针对内网 Coremail 服务器一键探测实际开放的收发端口（解决内网未开 SSL 993/465 而是开 143/25 的情况）
    """
    clean_host, _ = normalize_host_and_port(raw_host, 143)
    if not clean_host:
        return {"ok": False, "msg": "服务器地址不能为空，请填写论客客户端中的服务器 IP 或域名。"}

    # 第一步：验证 DNS / IP 解析（捕获 Errno 11001）
    try:
        resolved_ip = socket.gethostbyname(clean_host)
    except socket.gaierror as e:
        return {
            "ok": False,
            "msg": (
                f"无法解析服务器地址「{clean_host}」(错误码: {e.errno})。\n"
                f"原因：当前内网 DNS 无法识别该域名，或地址包含了特殊字符。\n"
                f"建议：请打开论客客户端【设置 -> 帐号管理】查看服务器地址，或直接填写邮件服务器的内网 IP 地址。"
            )
        }

    def is_port_open(port: int) -> bool:
        try:
            with socket.create_connection((resolved_ip, port), timeout=2.0):
                return True
        except Exception:
            return False

    # 第二步：探测 IMAP 端口（优先 993 SSL，其次 143 明文）
    if is_port_open(993):
        imap_port, imap_ssl = 993, True
    elif is_port_open(143):
        imap_port, imap_ssl = 143, False
    else:
        imap_port, imap_ssl = 143, False

    # 第三步：探测 SMTP 端口（优先 465 SSL，其次 25 明文，再次 587）
    if is_port_open(465):
        smtp_port, smtp_ssl = 465, True
    elif is_port_open(25):
        smtp_port, smtp_ssl = 25, False
    elif is_port_open(587):
        smtp_port, smtp_ssl = 587, False
    else:
        smtp_port, smtp_ssl = 25, False

    return {
        "ok": True,
        "host": clean_host,
        "resolved_ip": resolved_ip,
        "imap_port": imap_port,
        "imap_ssl": imap_ssl,
        "smtp_port": smtp_port,
        "smtp_ssl": smtp_ssl,
        "msg": f"探测成功 ({resolved_ip})：推荐 IMAP 端口 {imap_port} (SSL={imap_ssl})，SMTP 端口 {smtp_port} (SSL={smtp_ssl})"
    }
```
