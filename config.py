import os
import shutil
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent

# 数据与运行时目录（固定于 Windows 用户标准目录 %LOCALAPPDATA%\CoremailAssistant\data，跨版本升级永久保留）
appdata_root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
DATA_DIR = Path(appdata_root) / "CoremailAssistant" / "data"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
LOGS_DIR = Path(appdata_root) / "CoremailAssistant" / "logs"

# 数据库与本地机器学习模型存储路径
DATABASE_PATH = str(DATA_DIR / "assistant.db")
ML_MODELS_PATH = str(DATA_DIR / "ml_models.pkl")

# 自动创建必要目录
DATA_DIR.mkdir(parents=True, exist_ok=True)
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# 自动检测并迁移旧版本相对路径下的数据
def _migrate_legacy_data():
    legacy_candidates = [
        BASE_DIR / "data",
        Path(os.path.abspath("data"))
    ]
    target_db = Path(DATABASE_PATH)
    for leg_dir in legacy_candidates:
        try:
            if not leg_dir.exists() or leg_dir.resolve() == DATA_DIR.resolve():
                continue
            leg_db = leg_dir / "assistant.db"
            if leg_db.is_file() and leg_db.stat().st_size > 0:
                should_copy = False
                if not target_db.exists() or target_db.stat().st_size == 0:
                    should_copy = True
                elif leg_db.stat().st_mtime > target_db.stat().st_mtime or leg_db.stat().st_size > target_db.stat().st_size:
                    should_copy = True
                if should_copy:
                    shutil.copy2(str(leg_db), str(target_db))

            leg_ml = leg_dir / "ml_models.pkl"
            target_ml = Path(ML_MODELS_PATH)
            if leg_ml.is_file() and (not target_ml.exists() or leg_ml.stat().st_mtime > target_ml.stat().st_mtime):
                shutil.copy2(str(leg_ml), str(target_ml))

            leg_att = leg_dir / "attachments"
            if leg_att.is_dir():
                for item in leg_att.iterdir():
                    dst_item = ATTACHMENTS_DIR / item.name
                    if not dst_item.exists():
                        if item.is_dir():
                            shutil.copytree(str(item), str(dst_item))
                        else:
                            shutil.copy2(str(item), str(dst_item))
        except Exception:
            pass

_migrate_legacy_data()

# 默认系统配置项字典（用于数据库首次初始化或配置回退）
DEFAULT_SETTINGS = {
    # 论客邮箱 (Coremail) 协议与统一服务器配置 (适配论客客户端专用协议与单地址模式)
    "protocol_mode": "coremail",         # 'coremail': 专用单地址协议 (同论客客户端), 'imap_smtp': 标准手动端口
    "coremail_server": "",               # Coremail 统一服务器地址 (IP或域名)
    "http_base_url": "",                 # Coremail WebAPI 探测或指定的根 URL (如 http://10.x.x.x:8080)

    # 论客邮箱 (Coremail) IMAP 收信服务
    "imap_host": "mail.example.com",
    "imap_port": "993",
    "imap_ssl": "1",                     # 1: 启用 SSL, 0: 普通

    # 论客邮箱 (Coremail) SMTP 发信服务
    "smtp_host": "mail.example.com",
    "smtp_port": "465",
    "smtp_ssl": "1",                     # 1: 启用 SSL, 0: 普通

    # 账号凭据
    "email_account": "",
    "email_password": "",
    "sender_display_name": "",

    # 自动化与后台轮询
    "poll_interval": "60",               # 后台自动收信轮询间隔 (秒)
    "auto_mark_read": "0",              # 1: 流转后自动标记已读, 0: 保持原状态
    "max_fetch_count": "30",            # 单次拉取最大历史未读数

    # 过滤与智能化筛选模式
    # 可选值:
    #   'rules_and_ml': 优先规则匹配，未命中则调用本地机器学习
    #   'ml_only': 仅使用本地全文机器学习
    #   'rules_only': 仅使用规则匹配
    #   'ollama_hybrid': 本地初筛命中后调用 Ollama 大模型深度润色
    "filter_mode": "rules_and_ml",

    # 本地大模型 (Ollama) 配置
    "ollama_enabled": "0",              # 1: 启用, 0: 禁用
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "qwen2.5:3b",
    "ollama_timeout": "30",

    # 默认发信抄送习惯
    "default_include_sender_in_cc": "1", # 1: 默认抄送原发件人, 0: 不抄送
}
