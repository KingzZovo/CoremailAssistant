"""CoremailAssistant desktop application entrypoint.
Initializes High-DPI scaling, SQLite database schema, Windows 11 Fluent theme, and Main Window.
"""

import sys
import os
from pathlib import Path

# 将项目根目录加入模块搜索路径
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import QApplication

from core.database import DatabaseManager
from ui.theme import APP_QSS
from ui.main_window import MainWindow


def main():
    # 启用 Windows 高分屏 (High-DPI) 缩放与矢量图标支持
    QCoreApplication.setApplicationName("CoremailAssistant")
    QCoreApplication.setOrganizationName("CoremailAssistant")

    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)

    # 预初始化本地 SQLite 数据库与默认配置
    DatabaseManager()

    # 启动主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
