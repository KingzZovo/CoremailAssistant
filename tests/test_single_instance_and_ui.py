"""Tests for single instance application lock and navigation layout."""

import unittest
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from ui.theme import APP_QSS
from ui.main_window import MainWindow
from main import SINGLE_INSTANCE_SERVER_NAME


class TestSingleInstanceAndUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)
        cls.app.setStyleSheet(APP_QSS)

    def test_main_window_layout_and_buttons(self):
        """Verify navigation buttons, classes, and view switching."""
        window = MainWindow()
        # Verify object names and classes
        self.assertEqual(window.btn_sync_now.objectName(), "btn_sync_now")
        self.assertEqual(window.btn_new_memo.objectName(), "btn_new_memo")
        self.assertEqual(window.btn_view_pending.property("class"), "nav_item")
        self.assertEqual(window.btn_view_all.property("class"), "nav_item")
        self.assertEqual(window.btn_view_memos.property("class"), "nav_item")
        self.assertEqual(window.btn_open_rules.property("class"), "nav_util_btn")
        self.assertEqual(window.btn_open_settings.property("class"), "nav_util_btn")

        # Test view header
        self.assertTrue(hasattr(window, "view_title_lbl"))
        self.assertTrue(hasattr(window, "view_count_lbl"))

        # Switch to memos view
        window.btn_view_memos.click()
        self.assertEqual(window.current_view, "memos")
        self.assertEqual(window.view_title_lbl.text(), "📝 自定义备忘录")

        # Switch back to pending view
        window.btn_view_pending.click()
        self.assertEqual(window.current_view, "pending")
        self.assertEqual(window.view_title_lbl.text(), "📥 待流转协同")

        # Test wake_up
        window.showMinimized()
        self.assertTrue(window.isMinimized())
        window.wake_up()
        self.assertFalse(window.isMinimized())
        window.close()

    def test_single_instance_lock_socket(self):
        """Verify QLocalServer and QLocalSocket wake-up flow."""
        test_server_name = "CoremailAssistant_UnitTest_Lock"
        QLocalServer.removeServer(test_server_name)
        server = QLocalServer()
        self.assertTrue(server.listen(test_server_name))

        wake_called = []

        def on_new_conn():
            sock = server.nextPendingConnection()
            if sock:
                sock.waitForReadyRead(500)
                msg = sock.readAll()
                sock.disconnectFromServer()
                wake_called.append(bytes(msg))

        server.newConnection.connect(on_new_conn)

        # Simulate second instance connecting
        client = QLocalSocket()
        client.connectToServer(test_server_name)
        self.assertTrue(client.waitForConnected(500))
        client.write(b"WAKEUP\n")
        client.waitForBytesWritten(500)
        client.disconnectFromServer()

        self.app.processEvents()
        self.assertEqual(len(wake_called), 1)
        self.assertEqual(wake_called[0].strip(), b"WAKEUP")

        server.close()
        QLocalServer.removeServer(test_server_name)


if __name__ == "__main__":
    unittest.main()
