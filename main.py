"""CoremailAssistant desktop application entrypoint.
Initializes High-DPI scaling, Single-Instance lock, SQLite database schema, Windows 11 Fluent theme, and Main Window.
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
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from core.database import DatabaseManager
from ui.theme import APP_QSS
from ui.main_window import MainWindow

SINGLE_INSTANCE_SERVER_NAME = "CoremailAssistant_SingleInstance_App_Lock"


def main():
    # 启用 Windows 高分屏 (High-DPI) 缩放与矢量图标支持
    QCoreApplication.setApplicationName("CoremailAssistant")
    QCoreApplication.setOrganizationName("CoremailAssistant")

    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)

    # 1. 单实例检查：尝试连接已有的本地服务端
    client_socket = QLocalSocket()
    client_socket.connectToServer(SINGLE_INSTANCE_SERVER_NAME)
    if client_socket.waitForConnected(500):
        # 已有运行中的实例，向其发送唤醒信号后直接退出当前重复进程
        client_socket.write(b"WAKEUP\n")
        client_socket.waitForBytesWritten(500)
        client_socket.disconnectFromServer()
        sys.exit(0)

    # 2. 当前为首个实例，建立本地服务监听后续启动唤醒
    QLocalServer.removeServer(SINGLE_INSTANCE_SERVER_NAME)
    server = QLocalServer()
    if not server.listen(SINGLE_INSTANCE_SERVER_NAME):
        # 若初次监听失败，尝试强制清除残留后再次监听
        QLocalServer.removeServer(SINGLE_INSTANCE_SERVER_NAME)
        server.listen(SINGLE_INSTANCE_SERVER_NAME)

    # 预初始化本地 SQLite 数据库与默认配置
    DatabaseManager()

    # 提前在主线程预热加载 jieba 词典与机器学习引擎（防止子线程冷启动大词典引发 Windows 栈溢出崩溃）
    try:
        import jieba
        jieba.initialize()
    except Exception:
        pass
    try:
        from core.ml_learner import LocalEmailLearner
        LocalEmailLearner()
    except Exception:
        pass

    # 启动主窗口
    window = MainWindow()
    window.show()

    def handle_incoming_connection():
        sock = server.nextPendingConnection()
        if sock:
            sock.waitForReadyRead(500)
            sock.readAll()
            sock.disconnectFromServer()
            window.wake_up()

    server.newConnection.connect(handle_incoming_connection)

    # 保证 server 对象在事件循环生命周期中不被垃圾回收
    app._single_instance_server = server

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
