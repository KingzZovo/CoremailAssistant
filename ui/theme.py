"""Windows 11 Fluent Modern Light Card theme QSS stylesheet for CoremailAssistant."""

APP_QSS = """
/* 全局基础设置 */
* {
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    font-size: 13px;
    color: #1F2937;
}

QMainWindow, QDialog {
    background-color: #F8FAFC;
}

QWidget {
    outline: none;
}

/* 顶部导航与工具栏 */
QToolBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
    spacing: 6px;
    padding: 6px 10px;
}

QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 8px;
    font-weight: 500;
}

QToolButton:hover {
    background-color: #F1F5F9;
    border-color: #E2E8F0;
}

QToolButton:checked, QToolButton:pressed {
    background-color: #E2E8F0;
    border-color: #CBD5E1;
}

/* 主推按钮样式 */
QPushButton {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #F9FAFB;
    border-color: #9CA3AF;
}

QPushButton:pressed {
    background-color: #F3F4F6;
}

QPushButton:disabled {
    background-color: #F3F4F6;
    color: #9CA3AF;
    border-color: #E5E7EB;
}

/* 主色调高亮按钮 (Fluent Blue) */
QPushButton#btn_primary, QPushButton[primary="true"] {
    background-color: #2563EB;
    color: #FFFFFF;
    border: 1px solid #1D4ED8;
    font-weight: 600;
}

QPushButton#btn_primary:hover, QPushButton[primary="true"]:hover {
    background-color: #1D4ED8;
}

QPushButton#btn_primary:pressed, QPushButton[primary="true"]:pressed {
    background-color: #1E40AF;
}

/* 警示与忽略按钮 */
QPushButton#btn_danger, QPushButton[danger="true"] {
    background-color: #FEF2F2;
    color: #DC2626;
    border: 1px solid #FCA5A5;
}

QPushButton#btn_danger:hover, QPushButton[danger="true"]:hover {
    background-color: #FEE2E2;
}

/* 输入框与富文本框 */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #BFDBFE;
    selection-color: #1E3A8A;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1.5px solid #2563EB;
}

/* 下拉选择框 */
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: none;
}

QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: #EFF6FF;
    selection-color: #1D4ED8;
}

/* 列表与表格卡片化 */
QListWidget, QTableWidget, QTreeWidget {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 4px;
    alternate-background-color: #F8FAFC;
}

QListWidget::item, QTableWidget::item {
    border-radius: 6px;
    padding: 8px;
    margin: 2px 0;
}

QListWidget::item:hover, QTableWidget::item:hover {
    background-color: #F1F5F9;
}

QListWidget::item:selected, QTableWidget::item:selected {
    background-color: #EFF6FF;
    color: #1D4ED8;
}

/* 表格表头 */
QHeaderView::section {
    background-color: #F8FAFC;
    color: #475569;
    font-weight: 600;
    padding: 6px 10px;
    border: none;
    border-bottom: 1px solid #E2E8F0;
}

/* 滚动条美化 */
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #CBD5E1;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: transparent;
    height: 8px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #CBD5E1;
    min-width: 24px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #94A3B8;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* 选项卡 (Tabs) */
QTabWidget::pane {
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    background-color: #FFFFFF;
    top: -1px;
}

QTabBar::tab {
    background-color: transparent;
    padding: 8px 16px;
    margin-right: 4px;
    font-weight: 500;
    border-bottom: 2px solid transparent;
}

QTabBar::tab:hover {
    color: #2563EB;
}

QTabBar::tab:selected {
    color: #2563EB;
    font-weight: 600;
    border-bottom: 2px solid #2563EB;
}

/* 分组框 (GroupBox) */
QGroupBox {
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 14px;
    background-color: #FFFFFF;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 12px;
    color: #334155;
}

/* 复选框与单选按钮 */
QCheckBox, QRadioButton {
    spacing: 6px;
    font-size: 13px;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
}

/* 分割条 (Splitter) */
QSplitter::handle {
    background-color: #E2E8F0;
}

QSplitter::handle:horizontal {
    width: 2px;
}

QSplitter::handle:vertical {
    height: 2px;
}

/* 状态栏 */
QStatusBar {
    background-color: #FFFFFF;
    border-top: 1px solid #E2E8F0;
    color: #64748B;
    font-size: 12px;
}
"""
