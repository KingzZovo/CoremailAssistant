"""Coremail-style WYSIWYG Rich Text Email Editor component.
Features format toolbar, tables, color highlight, and direct Ctrl+V screenshot pasting.
"""

import base64
from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice
from PySide6.QtGui import (
    QFont, QTextCharFormat, QColor, QTextCursor, QTextListFormat,
    QTextTableFormat, QTextLength, QAction, QImage
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QFontComboBox,
    QComboBox, QTextEdit, QColorDialog, QFileDialog, QInputDialog
)


class pasteableTextEdit(QTextEdit):
    """支持直接 Ctrl+V 粘贴剪贴板截图/图片并自动转为内嵌 HTML Base64 的富文本编辑框"""

    def canInsertFromMimeData(self, source) -> bool:
        if source.hasImage():
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source) -> None:
        if source.hasImage():
            image = QImage(source.imageData())
            if not image.isNull():
                ba = QByteArray()
                buf = QBuffer(ba)
                buf.open(QIODevice.WriteOnly)
                image.save(buf, "PNG")
                b64_str = ba.toBase64().data().decode("ascii")
                self.textCursor().insertHtml(
                    f'<img src="data:image/png;base64,{b64_str}" style="max-width:100%; margin: 6px 0;" />'
                )
                return
        super().insertFromMimeData(source)


class RichTextMailEditor(QWidget):
    """仿 Coremail 论客客户端的所见即所得富文本邮件编辑器组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 富文本编辑区主体（先初始化以便工具栏信号绑定）
        self.editor = pasteableTextEdit()
        self.editor.setAcceptRichText(True)
        self.editor.setStyleSheet(
            "QTextEdit { background: #FFFFFF; border: 1px solid #D1D5DB; border-radius: 6px; padding: 10px; font-size: 14px; line-height: 1.6; }"
        )

        # 顶部富文本格式工具栏
        self.toolbar = QToolBar()
        self.toolbar.setStyleSheet(
            "QToolBar { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 3px; spacing: 4px; }"
        )

        # 1. 字体选择
        self.font_box = QFontComboBox()
        self.font_box.setMaximumWidth(150)
        self.font_box.setCurrentFont(QFont("Microsoft YaHei"))
        self.font_box.currentFontChanged.connect(self._on_font_changed)
        self.toolbar.addWidget(self.font_box)

        # 2. 字号选择
        self.size_box = QComboBox()
        for sz in ["9", "10", "11", "12", "14", "16", "18", "20", "24", "28"]:
            self.size_box.addItem(f"{sz} pt", int(sz))
        self.size_box.setCurrentIndex(4)  # 默认 14pt
        self.size_box.currentIndexChanged.connect(self._on_size_changed)
        self.toolbar.addWidget(self.size_box)
        self.toolbar.addSeparator()

        # 3. 粗体 / 斜体 / 下划线 / 删除线
        self.act_bold = QAction("B 加粗", self, checkable=True)
        self.act_bold.triggered.connect(lambda checked: self.editor.setFontWeight(QFont.Bold if checked else QFont.Normal))
        self.toolbar.addAction(self.act_bold)

        self.act_italic = QAction("I 斜体", self, checkable=True)
        self.act_italic.triggered.connect(self.editor.setFontItalic)
        self.toolbar.addAction(self.act_italic)

        self.act_underline = QAction("U 下划线", self, checkable=True)
        self.act_underline.triggered.connect(self.editor.setFontUnderline)
        self.toolbar.addAction(self.act_underline)

        self.act_strike = QAction("S 删除线", self, checkable=True)
        self.act_strike.triggered.connect(self._toggle_strike)
        self.toolbar.addAction(self.act_strike)
        self.toolbar.addSeparator()

        # 4. 字体颜色 / 标红 / 荧光笔标黄 / 选择颜色
        act_red = QAction("🔴 标红", self)
        act_red.triggered.connect(lambda: self.editor.setTextColor(QColor("#DC2626")))
        self.toolbar.addAction(act_red)

        act_highlight = QAction("🟨 标黄高亮", self)
        act_highlight.triggered.connect(self._toggle_yellow_highlight)
        self.toolbar.addAction(act_highlight)

        act_color = QAction("🎨 文字颜色", self)
        act_color.triggered.connect(self._choose_text_color)
        self.toolbar.addAction(act_color)
        self.toolbar.addSeparator()

        # 5. 对齐与列表
        act_left = QAction("左对齐", self)
        act_left.triggered.connect(lambda: self.editor.setAlignment(Qt.AlignLeft))
        self.toolbar.addAction(act_left)

        act_center = QAction("居中", self)
        act_center.triggered.connect(lambda: self.editor.setAlignment(Qt.AlignCenter))
        self.toolbar.addAction(act_center)

        act_bullet = QAction("• 项目列表", self)
        act_bullet.triggered.connect(lambda: self._insert_list(QTextListFormat.ListDisc))
        self.toolbar.addAction(act_bullet)

        act_num = QAction("1. 编号列表", self)
        act_num.triggered.connect(lambda: self._insert_list(QTextListFormat.ListDecimal))
        self.toolbar.addAction(act_num)
        self.toolbar.addSeparator()

        # 6. 插入表格 / 插入图片 / 清除格式
        act_table = QAction("📅 插入表格", self)
        act_table.triggered.connect(self._insert_table)
        self.toolbar.addAction(act_table)

        act_img = QAction("🖼️ 插入图片", self)
        act_img.triggered.connect(self._insert_image_file)
        self.toolbar.addAction(act_img)

        act_clear = QAction("🧹 清除格式", self)
        act_clear.triggered.connect(self._clear_formatting)
        self.toolbar.addAction(act_clear)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.editor, 1)

    def _on_font_changed(self, font: QFont):
        fmt = QTextCharFormat()
        fmt.setFontFamilies([font.family()])
        self.editor.mergeCurrentCharFormat(fmt)

    def _on_size_changed(self, idx: int):
        sz = self.size_box.itemData(idx)
        if sz:
            self.editor.setFontPointSize(float(sz))

    def _toggle_strike(self, checked: bool):
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(checked)
        self.editor.mergeCurrentCharFormat(fmt)

    def _toggle_yellow_highlight(self):
        cursor = self.editor.textCursor()
        curr_bg = cursor.charFormat().background().color()
        fmt = QTextCharFormat()
        if curr_bg == QColor("#FEF08A"):
            fmt.setBackground(Qt.transparent)
        else:
            fmt.setBackground(QColor("#FEF08A"))
        self.editor.mergeCurrentCharFormat(fmt)

    def _choose_text_color(self):
        color = QColorDialog.getColor(self.editor.textColor(), self, "选择文字颜色")
        if color.isValid():
            self.editor.setTextColor(color)

    def _insert_list(self, style: QTextListFormat.Style):
        cursor = self.editor.textCursor()
        cursor.createList(style)

    def _insert_table(self):
        rows, ok1 = QInputDialog.getInt(self, "插入表格", "行数:", 3, 1, 30)
        if not ok1:
            return
        cols, ok2 = QInputDialog.getInt(self, "插入表格", "列数:", 3, 1, 15)
        if not ok2:
            return
        fmt = QTextTableFormat()
        fmt.setBorder(1)
        fmt.setCellPadding(6)
        fmt.setCellSpacing(0)
        fmt.setWidth(QTextLength(QTextLength.PercentageLength, 100))
        self.editor.textCursor().insertTable(rows, cols, fmt)

    def _insert_image_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择要插入正文的图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.gif)")
        if path:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            ext = path.rsplit(".", 1)[-1].lower()
            self.editor.textCursor().insertHtml(f'<img src="data:image/{ext};base64,{b64}" style="max-width:100%;" />')

    def _clear_formatting(self):
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        cursor.setCharFormat(fmt)

    def set_html(self, html_content: str):
        self.editor.setHtml(html_content or "")

    def get_html(self) -> str:
        return self.editor.toHtml()

    def get_plain_text(self) -> str:
        return self.editor.toPlainText()

    def set_plain_text(self, text: str):
        self.editor.setPlainText(text or "")
