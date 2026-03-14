"""
可折叠面板组件
"""
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSizePolicy, QScrollArea
)


class CollapsibleBox(QWidget):
    """简洁科技感的可折叠面板"""

    def __init__(self, title: str = "", parent: QWidget = None):
        super().__init__(parent)
        self._is_collapsed = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── 标题栏 ──────────────────────────────────
        self._header = QWidget()
        self._header.setFixedHeight(40)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #e4e7eb;
                border-radius: 8px;
            }
        """)

        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(14, 0, 14, 0)
        header_layout.setSpacing(8)

        self._arrow = QLabel("▾")
        self._arrow.setStyleSheet(
            "color: #6366f1; font-size: 16px; background: transparent; border: none;"
        )

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet(
            "font-weight: 600; font-size: 14px; color: #1f2937;"
            "background: transparent; border: none;"
        )

        header_layout.addWidget(self._arrow)
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        # ── 内容区 ──────────────────────────────────
        self._body = QWidget()
        self._body.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #e4e7eb;
                border-top: none;
                border-radius: 0px 0px 8px 8px;
            }
        """)

        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(16, 12, 16, 16)
        self._body_layout.setSpacing(10)

        # ── 动画 ────────────────────────────────────
        self._anim = QPropertyAnimation(self._body, b"maximumHeight")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        outer.addWidget(self._header)
        outer.addWidget(self._body)

        # 标题栏点击事件
        self._header.mousePressEvent = lambda _: self.toggle()

    # ── 公开接口 ─────────────────────────────────────

    def add_widget(self, widget: QWidget):
        self._body_layout.addWidget(widget)

    def add_layout(self, layout):
        self._body_layout.addLayout(layout)

    def toggle(self):
        if self._is_collapsed:
            self._expand()
        else:
            self._collapse()

    # ── 内部方法 ─────────────────────────────────────

    def _collapse(self):
        self._is_collapsed = True
        self._arrow.setText("▸")
        # 圆角恢复完整（折叠后 header 是独立的圆角卡片）
        self._header.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #e4e7eb;
                border-radius: 8px;
            }
        """)
        self._anim.setStartValue(self._body.height())
        self._anim.setEndValue(0)
        self._anim.start()

    def _expand(self):
        self._is_collapsed = False
        self._arrow.setText("▾")
        # header 底部直角，接内容区
        self._header.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #e4e7eb;
                border-bottom: none;
                border-radius: 8px 8px 0px 0px;
            }
        """)
        target = self._body.sizeHint().height()
        self._anim.setStartValue(0)
        self._anim.setEndValue(max(target, 50))
        self._anim.start()
