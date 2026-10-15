# CoremailAssistant (论客邮箱智能协同与邮件自动处理助手)

[![GitHub Release](https://img.shields.io/github/v/release/KingzZovo/CoremailAssistant?color=blue&logo=github)](https://github.com/KingzZovo/CoremailAssistant/releases)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![UI Framework](https://img.shields.io/badge/UI-PySide6%20(Qt6)-green.svg)](https://wiki.qt.io/Qt_for_Python)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-lightgrey.svg)](https://www.microsoft.com/windows)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

专门针对 **Windows 环境** 与 **论客邮箱 (Coremail 企业邮)** 打造的邮件自动化处理、智能协同流转与桌面工作台工具。专为企业纯内网环境设计（适配 10代 i5 / 16G 内存 / 无独显设备），支持未读邮件监听、全文特征增量机器学习、修改差异自学习、仿论客客户端富文本编辑器（支持截图直接粘贴内联图片）、附件自动继承与全功能备忘录工作台。

---

## 🌟 核心技术亮点与功能矩阵

| 核心模块 | 具体实现效果 | 智能化与防错机制 |
| :--- | :--- | :--- |
| **1. 论客邮件自动化处理** | 支持通过 IMAP/SMTP 协议进行高频/定时轮询，自动拉取未读邮件并完成规则解析与邮件流转。 | 深度兼容论客邮箱常见的 `GB18030` / `GBK` / `UTF-8` 编码，杜绝标题和附件名乱码。 |
| **2. 双模式邮件流转** | **模式 A（改写为全新邮件）**：剔除 `Fw:` 与原邮件引用头，改写主语/人称后作为全新邮件发送；**模式 B（标准转发）**：保留原引用头与完整正文。 | 抄送栏提供独立 `[✓] 抄送原发件人` 开关；常用联系人点选与抄送栏实时互斥去重。 |
| **3. 全文机器学习 + 全文 Diff 自学习** | ① **全文 TF-IDF 增量分类**：在线 `partial_fit` 训练，预测流转概率与推荐收件人；<br>② **称呼自适应**：无称呼时保护首句不误删；<br>③ **Diff 自学习**：对比原邮件与发出邮件，自动记忆用户改写习惯。 | 纯 CPU 全文特征提取，在线增量训练耗时 `< 10ms`，内存占用 `< 60MB`，完全不卡顿。 |
| **4. 仿论客客户端富文本编辑器** | 内置所见即所得 (WYSIWYG) 编辑器：字号、加粗、颜色高亮、表格、列表，支持直接 `Ctrl+V` 粘贴剪贴板截图。 | 正文粘贴的截图自动编码为 `MIMEImage (cid: 内联图片)`，确保对方在论客客户端中正常展示。 |
| **5. 附件管理与一键继承** | 无论是改写新建还是标准转发，原邮件自带附件均自动缓存到本地并默认全选挂载。 | 弹窗中可一键取消勾选无需发送的原附件，或点击“+ 添加本地附件”追加新文件。 |
| **6. 全功能自定义备忘录** | 既可由邮件一键提取生成备忘，也可点击“➕ 新建自定义备忘录”独立创建；支持富文本、子任务清单 (Checklist) 与置顶。 | 每 30 秒后台静默检查到期备忘，通过 Windows 系统托盘弹出气泡通知。 |
| **7. 本地大模型扩展 (可选)** | 支持无缝接入本地 Ollama（如 `qwen2.5:3b` / `qwen2.5:1.5b`）进行深度主语润色与摘要。 | 采用降级设计：未启动 Ollama 时自动使用本地机器学习与规则引擎，绝不阻塞主流程。 |

---

## 📁 项目目录结构

```text
CoremailAssistant/
├── main.py                      # 桌面程序入口，初始化高分屏缩放、数据库、主窗口与系统托盘
├── config.py                    # 默认配置常量、全局目录路径与 DEFAULT_SETTINGS
├── requirements.txt             # 核心生产依赖清单 (PySide6, scikit-learn, jieba, beautifulsoup4 等)
├── requirements-dev.txt         # 开发与代码检查依赖
├── pyproject.toml               # 项目打包元数据与构建配置
├── .env.example                 # 环境变量凭据模板 (敏感账号信息)
├── .gitignore                   # Git 忽略配置 (已排除本地数据库、模型与敏感文件)
├── LICENSE                      # MIT 开源协议
├── README.md                    # 项目说明文档
│
├── core/                        # 核心业务逻辑层
│   ├── __init__.py
│   ├── database.py              # SQLite 数据库访问层 (7 张核心表 CRUD 与全文 Diff 学习记录)
│   ├── mail_client.py           # Coremail IMAP 收信解析、附件落盘、SMTP 富文本+内联图片发信引擎
│   ├── rewriter_engine.py       # 全文主语/人称改写、无称呼/带称呼自适应处理、HTML保留改写
│   ├── ml_learner.py            # 全文 N-Gram 在线机器学习引擎 + 全文修改差异 (Diff) 自动提取学习器
│   ├── ollama_client.py         # 本地 Ollama 接口封装 (全文摘要提取 + 复杂全文主语润色)
│   └── worker_threads.py        # QThread 后台异步线程 (异步收信、增量学习、发信)
│
├── ui/                          # PySide6 图形界面层
│   ├── __init__.py
│   ├── theme.py                 # Windows 11 Fluent 现代浅色卡片风格 QSS 样式表
│   ├── rich_text_editor.py      # 仿论客客户端富文本编辑器 (格式工具栏、表格、截图粘贴)
│   ├── compose_send_dialog.py   # 双模式发信确认台 (新建改写/转发切换、联系人联动、附件增删)
│   ├── memo_dialog.py           # 全功能自定义备忘录弹窗 (富文本内容、子任务 Checklist、到期提醒)
│   ├── rule_contact_dialog.py   # 常用联系人 (专属称呼/是否加称呼习惯)、改写词典与规则管理
│   ├── settings_dialog.py       # 论客 IMAP/SMTP 配置、全文机器学习状态面板、Ollama 配置
│   └── main_window.py           # 三栏式主窗口 (左侧导航 + 中间邮件/备忘列表 + 右侧详情与流转台)
│
├── data/                        # 本地运行时数据目录 (.gitignore 排除)
│   ├── assistant.db             # SQLite 本地数据库 (7 张表)
│   ├── ml_models.pkl            # joblib 持久化的全文增量机器学习模型文件
│   └── attachments/             # 按邮件 UID 分类缓存的原邮件附件与内联图片
│
├── scripts/                     # Windows 自动化批处理脚本
│   ├── install_windows.bat      # Windows 一键创建虚拟环境并安装依赖
│   └── run_windows.bat          # Windows 一键启动桌面客户端
│
└── tests/                       # 单元测试套件
    ├── __init__.py
    ├── test_parser.py           # 编码解码与邮件解析测试
    └── test_rules.py            # 规则匹配与条件引擎测试
```

---

## 📥 下载地址与打包发布 (GitHub Releases)

前往 GitHub 官方 Releases 页面直接下载已打包版本：
👉 **[下载最新发布版本 (Releases)](https://github.com/KingzZovo/CoremailAssistant/releases)**

| 下载文件 | 文件大小 | 说明与特性 | 适用场景 |
| :--- | :--- | :--- | :--- |
| **`CoremailAssistant-Setup-vX.X.X.exe`** | **~35MB - 50MB** | **【强烈推荐】单文件安装向导**：基于 Inno Setup 固实 LZMA2 极限压缩，体积相比普通 Zip 直降 85%+；一键安装，自动创建桌面与开始菜单快捷方式，无需管理员 UAC 权限，升级时自动关闭旧版本保护数据 | 绝大多数 Windows 最终用户 |
| **`CoremailAssistant-vX.X.X-Portable.7z`** | **~35MB - 55MB** | **绿色便携版 (7-Zip 固实极高压缩)**：免安装，解压到任意目录双击即可运行，体积超小 | 偏好纯绿色软件、存放在 U盘/移动硬盘的用户 |
| **`CoremailAssistant-vX.X.X-Windows-x64.zip`** | **~60MB - 90MB** | **通用 Zip 便携版 (7-Zip 优化压缩)**：无需安装任何解压软件，Windows 系统原生右键解压即用 | 无法运行 7z 或受公司软件安装限制的环境 |
| **`CoremailAssistant-vX.X.X-Portable.zip`** | **~120KB** | **纯源码便携包**：内含 Windows 一键安装与启动脚本（`一键安装并启动.bat`，支持清华源与内网 wheels 离线安装） | 开发者 / 需要二次开发或调试的用户 |

---

## 🚀 Windows 快速上手指南

### 第一步：克隆代码或解压源码包
将项目保存至本地磁盘（例如 `D:\Projects\CoremailAssistant`）。

### 第二步：一键初始化环境
在项目根目录中，直接双击运行：
```cmd
scripts\install_windows.bat
```
脚本将全自动完成：
1. 校验本地 Python 3.9+ 环境；
2. 建立独立虚拟环境 `.venv`；
3. 一键安装 PySide6、scikit-learn、jieba 等完整依赖；
4. 自动创建所需数据目录 `data/`、`data/attachments/` 与 `logs/`。

### 第三步：配置论客邮箱
双击启动 `scripts\run_windows.bat`，在主界面点击左下角 **“⚙️ 系统设置”**：
- **协议类型**：默认选用 **`Coremail 专用协议（同论客客户端）`**。
- **服务器地址**：直接复制论客客户端【设置 -> 帐号管理】里的服务器 IP 或域名（如 `192.168.1.50` 或 `mail.company.com`，系统会自动清洗 `http://`、路径与多余端口）。
- 点击 **“🔍 自动检测端口与连接”**，系统会自动探测内网开放的端口（支持 993/465 SSL 与 143/25 内网明文自动适配降级）。
- **邮箱账号与密码**：填写您的论客邮箱账号和密码（若开启双重验证，请填写专用授权码）。
- 点击 **“测试连接”**，验证收发均正常后点击保存即可。

*(注：系统同样保留了 **IMAP/SMTP 标准协议** 模式，供需要精细自定义不同主机与独立端口的高级用户使用)*

---

## 📦 推送到 GitHub 仓库

如果你需要将本项目上传到 GitHub：

```bash
# 1. 在 GitHub 上创建一个新的空白仓库（例如命名为 CoremailAssistant）

# 2. 进入本地项目目录
cd CoremailAssistant

# 3. 关联你的 GitHub 远程仓库 (将 USERNAME 替换为你的 GitHub 用户名)
git remote add origin https://github.com/USERNAME/CoremailAssistant.git

# 4. 确认主分支并推送
git branch -M main
git push -u origin main
```

> 🔒 **隐私安全提示**：
> 本项目的 `.gitignore` 已预先配置严格的安全规则，您的账号密码、本地邮件缓存（`data/attachments/`）、SQLite 数据库（`data/assistant.db`）以及本地日志均不会被推送到 GitHub。

---

## 🧪 单元测试

在开发或 CI 自动化流程中执行测试：
```bash
python -m unittest discover -s tests
```

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源。
