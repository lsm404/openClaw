"""
OpenClaw 小说写作助手 - 桌面应用
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QRectF, QSettings, QTimer, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .collapsible_box import CollapsibleBox
from .config import load_config, OpenClawConfig
from .novel_generator import generate_chapter_summary, generate_next_chapter
from .novel_store import Chapter, Novel, create_novel, list_novels, load_novel, save_novel


class LoadingSpinner(QWidget):
    def __init__(self, size: int = 56, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._size = size
        self._angle = 0
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _tick(self) -> None:
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event: QEvent) -> None:
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._size
        pad = 5
        rect = QRectF(pad, pad, s - pad * 2, s - pad * 2)
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QColor(99, 102, 241, 230))
        qp.drawEllipse(rect)
        pen = QPen(QColor(255, 255, 255, 50), 5, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        qp.setPen(pen)
        qp.drawArc(rect.toRect(), 0, 360 * 16)
        arc_len = 270
        steps = 18
        for i in range(steps):
            alpha = int(255 * (i + 1) / steps)
            color = QColor(255, 255, 255, alpha)
            pen = QPen(color, 6, Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            qp.setPen(pen)
            start = int((-self._angle - i * (arc_len / steps)) * 16)
            span = int(-(arc_len / steps) * 16)
            qp.drawArc(rect.toRect(), start, span)


class _DotLabel(QLabel):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._idx = 0
        self._base = ""
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(500)

    def set_base(self, text: str) -> None:
        self._base = text
        self._render()

    def _tick(self) -> None:
        self._idx = (self._idx + 1) % 4
        self._render()

    def _render(self) -> None:
        dots = "." * self._idx + "<span style='color:transparent'>." * (3 - self._idx) + "</span>"
        self.setText(f"<span>{self._base}</span>{dots}")


class LoadingOverlay(QWidget):
    def __init__(self, parent: QWidget, message: str = "加载中") -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setWindowOpacity(0.0)
        self.hide()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card = QFrame(self)
        card.setObjectName("LoadingCard")
        card.setStyleSheet("""
            #LoadingCard {
                background-color: rgba(99, 102, 241, 230);
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.3);
            }
        """)
        card.setMinimumWidth(220)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(36, 28, 36, 28)
        card_layout.setSpacing(20)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spinner = LoadingSpinner(56, card)
        card_layout.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        self._label = _DotLabel(card)
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setStyleSheet("color: rgba(230,230,230,220); font-size: 14px;")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.set_base(message)
        card_layout.addWidget(self._label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(card)
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.finished.connect(self._on_anim_done)

    def paintEvent(self, event: QEvent) -> None:
        qp = QPainter(self)
        qp.fillRect(self.rect(), QColor(0, 0, 0, 120))

    def set_message(self, text: str) -> None:
        self._label.set_base(text)

    def show_overlay(self, message: Optional[str] = None) -> None:
        if message is not None:
            self._label.set_base(message)
        self.setGeometry(self.parent().rect())
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(1.0)
        self.show()
        self._anim.start()

    def hide_overlay(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _on_anim_done(self) -> None:
        if self._effect.opacity() < 0.05:
            self.hide()


class NovelChapterWorker(QThread):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        novel: Novel,
        chapter_hint: str,
        config: OpenClawConfig,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._novel = novel
        self._chapter_hint = chapter_hint
        self._config = config

    def run(self) -> None:
        try:
            content = generate_next_chapter(
                self._config,
                self._novel,
                chapter_hint=self._chapter_hint,
            )
            self.finished.emit(content)
        except Exception as exc:
            self.failed.emit(str(exc))


class SummaryWorker(QThread):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, content: str, config: OpenClawConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._content = content
        self._config = config

    def run(self) -> None:
        try:
            summary = generate_chapter_summary(self._config, self._content)
            self.finished.emit(summary)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OpenClaw - 小说写作助手")
        self.setFixedSize(1100, 700)

        self._settings = QSettings("OpenClaw", "NovelWriter")
        self._novel: Optional[Novel] = None
        self._current_chapter_index: int = -1
        self._suppress_chapter_save: bool = False
        self._chapter_worker: Optional[NovelChapterWorker] = None
        self._summary_worker: Optional[SummaryWorker] = None

        self._apply_styles()
        self._build_ui()
        self._build_menu()

        # 启动时加载小说列表，若有则打开第一本
        novels = list_novels()
        if novels:
            self._open_novel(novels[0].id)
        else:
            self._show_create_novel_prompt()

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f7fa; }
            QGroupBox {
                background-color: white;
                border: 1px solid #e4e7eb;
                border-radius: 8px;
                padding: 12px;
            }
            QLineEdit, QPlainTextEdit {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 8px;
                background-color: white;
                font-size: 13px;
            }
            QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #6366f1; }
            QPushButton {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 8px 16px;
                background-color: white;
                font-size: 13px;
                color: #374151;
            }
            QPushButton:hover { background-color: #f3f4f6; border-color: #6366f1; }
            QPushButton:pressed { background-color: #e5e7eb; }
            QListWidget {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                background-color: white;
                padding: 4px;
            }
            QListWidget::item { padding: 8px; }
            QListWidget::item:selected { background-color: #e0e7ff; color: #4338ca; }
        """)

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        main = QHBoxLayout(central)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(12)

        # ── 左侧 ─────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(12)

        # 小说选择
        novel_row = QHBoxLayout()
        novel_row.addWidget(QLabel("小说："))
        self.novel_combo = QComboBox()
        self.novel_combo.setMinimumWidth(180)
        self.novel_combo.currentIndexChanged.connect(self._on_novel_selected)
        novel_row.addWidget(self.novel_combo)
        self.new_novel_btn = QPushButton("新建")
        self.new_novel_btn.clicked.connect(self._show_create_novel_prompt)
        novel_row.addWidget(self.new_novel_btn)
        left.addLayout(novel_row)

        # 小说配置
        self.config_box = CollapsibleBox("小说配置")
        self.config_box.add_widget(QLabel("标题"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("小说标题")
        self.config_box.add_widget(self.title_edit)
        self.config_box.add_widget(QLabel("类型"))
        self.genre_combo = QComboBox()
        self.genre_combo.addItem("短篇", "short")
        self.genre_combo.addItem("长篇", "long")
        self.config_box.add_widget(self.genre_combo)
        self.config_box.add_widget(QLabel("简介"))
        self.synopsis_edit = QPlainTextEdit()
        self.synopsis_edit.setPlaceholderText("故事简介、世界观等，人物由 AI 自动生成")
        self.synopsis_edit.setFixedHeight(80)
        self.config_box.add_widget(self.synopsis_edit)

        # 豆包配置
        ark_box = CollapsibleBox("模型配置")
        self.ark_api_key_edit = QLineEdit()
        self.ark_api_key_edit.setEchoMode(QLineEdit.Password)
        self.ark_api_key_edit.setPlaceholderText("豆包 Key")
        self.ark_model_edit = QLineEdit()
        self.ark_model_edit.setPlaceholderText("豆包模型 ID")
        self.enable_web_search_checkbox = QCheckBox("🌐 联网生成")
        self.enable_web_search_checkbox.setToolTip("开启后模型可联网搜索")
        ark_box.add_widget(QLabel("豆包 Key"))
        ark_box.add_widget(self.ark_api_key_edit)
        ark_box.add_widget(QLabel("豆包模型"))
        ark_box.add_widget(self.ark_model_edit)
        ark_box.add_widget(self.enable_web_search_checkbox)

        self.ark_api_key_edit.setText(self._settings.value("ark/api_key", os.getenv("ARK_API_KEY", "")))
        self.ark_model_edit.setText(self._settings.value("ark/model", os.getenv("ARK_MODEL", "")))
        self.enable_web_search_checkbox.setChecked(
            str(self._settings.value("ark/enable_web_search", "0")).lower() in {"1", "true", "yes"}
        )

        left.addWidget(self.config_box)
        left.addWidget(ark_box)

        # 章节列表
        left.addWidget(QLabel("章节"))
        self.chapter_list = QListWidget()
        self.chapter_list.setMinimumHeight(120)
        self.chapter_list.currentRowChanged.connect(self._on_chapter_selected)
        left.addWidget(self.chapter_list)

        main.addLayout(left, 1)

        # ── 右侧 ─────────────────────────────────────
        right = QVBoxLayout()

        # 本章梗概
        right.addWidget(QLabel("本章梗概（可选）"))
        self.chapter_hint_edit = QLineEdit()
        self.chapter_hint_edit.setPlaceholderText("如：第三章 - 主角初遇反派")
        right.addWidget(self.chapter_hint_edit)

        # 生成按钮
        self.generate_btn = QPushButton("✨ 生成下一章")
        self.generate_btn.setMinimumHeight(40)
        self.generate_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #667eea; color: white; font-weight: 600;"
            "  padding: 10px 24px; border: none; border-radius: 8px; font-size: 15px;"
            "}"
            "QPushButton:hover { background-color: #5568d3; }"
            "QPushButton:disabled { background-color: #e5e7eb; color: #9ca3af; }"
        )
        self.generate_btn.clicked.connect(self._on_generate_clicked)
        right.addWidget(self.generate_btn)

        # 正文
        right.addWidget(QLabel("正文"))
        self.content_edit = QPlainTextEdit()
        self.content_edit.setPlaceholderText("选中章节可编辑，或生成新章节")
        right.addWidget(self.content_edit)

        main.addLayout(right, 2)

        # 加载遮罩
        self._loading_overlay = LoadingOverlay(central, "正在生成...")
        self._loading_overlay.hide()

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("文件")
        save_action = QAction("导出为 Markdown...", self)
        save_action.triggered.connect(self._export_markdown)
        menu.addAction(save_action)

    def _refresh_novel_combo(self) -> None:
        self.novel_combo.clear()
        for n in list_novels():
            self.novel_combo.addItem(n.title, n.id)
        if self._novel:
            idx = self.novel_combo.findData(self._novel.id)
            if idx >= 0:
                self.novel_combo.setCurrentIndex(idx)

    def _show_create_novel_prompt(self) -> None:
        title, ok = QInputDialog.getText(self, "新建小说", "小说标题：")
        if not ok or not title.strip():
            return
        novel = create_novel(title=title.strip())
        self._refresh_novel_combo()
        self._open_novel(novel.id)

    def _open_novel(self, novel_id: str) -> None:
        novel = load_novel(novel_id)
        if not novel:
            return
        self._novel = novel
        self._refresh_novel_combo()
        self._load_novel_into_ui()
        self._refresh_chapter_list()

    def _on_novel_selected(self, index: int) -> None:
        if index < 0:
            return
        novel_id = self.novel_combo.currentData()
        if novel_id and (not self._novel or self._novel.id != novel_id):
            self._open_novel(novel_id)

    def _load_novel_into_ui(self) -> None:
        if not self._novel:
            return
        self.title_edit.setText(self._novel.title)
        idx = self.genre_combo.findData(self._novel.genre)
        if idx >= 0:
            self.genre_combo.setCurrentIndex(idx)
        self.synopsis_edit.setPlainText(self._novel.synopsis)

    def _save_novel_from_ui(self) -> None:
        if not self._novel:
            return
        self._novel.title = self.title_edit.text().strip()
        self._novel.genre = self.genre_combo.currentData() or "short"
        self._novel.synopsis = self.synopsis_edit.toPlainText().strip()
        save_novel(self._novel)

    def _refresh_chapter_list(self) -> None:
        self.chapter_list.blockSignals(True)
        self.chapter_list.clear()
        if self._novel:
            for c in self._novel.chapters:
                item = QListWidgetItem(f"第{c.order}章 {c.title or '(无标题)'}")
                item.setData(Qt.ItemDataRole.UserRole, c.id)
                self.chapter_list.addItem(item)
        self.chapter_list.blockSignals(False)

    def _on_chapter_selected(self, row: int) -> None:
        if not self._novel:
            return
        # 保存当前编辑到上一章（切换章节时）
        if not self._suppress_chapter_save and self._current_chapter_index >= 0 and self._current_chapter_index < len(self._novel.chapters):
            self._novel.chapters[self._current_chapter_index].content = self.content_edit.toPlainText()
            save_novel(self._novel)
        self._suppress_chapter_save = False
        if row < 0:
            self._current_chapter_index = -1
            self.content_edit.clear()
            return
        self._current_chapter_index = row
        ch = self._novel.chapters[row]
        self.content_edit.setPlainText(ch.content)

    def _on_generate_clicked(self) -> None:
        if not self._novel:
            QMessageBox.warning(self, "提示", "请先新建或选择一本小说。")
            return

        ark_key = self.ark_api_key_edit.text().strip()
        ark_model = self.ark_model_edit.text().strip()
        if not ark_key or not ark_model:
            QMessageBox.warning(self, "提示", "请填写豆包 Key 和模型 ID。")
            return

        self._save_novel_from_ui()
        self._save_ark_settings()

        config = OpenClawConfig(
            api_key=ark_key,
            base_url=os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").strip(),
            model=ark_model,
            enable_web_search=self.enable_web_search_checkbox.isChecked(),
        )

        chapter_hint = self.chapter_hint_edit.text().strip()
        self.generate_btn.setEnabled(False)
        self._loading_overlay.show_overlay("正在生成下一章...")

        self._chapter_worker = NovelChapterWorker(
            novel=self._novel,
            chapter_hint=chapter_hint,
            config=config,
            parent=self,
        )
        self._chapter_worker.finished.connect(self._on_chapter_generated)
        self._chapter_worker.failed.connect(self._on_chapter_failed)
        self._chapter_worker.start()

    def _on_chapter_generated(self, content: str) -> None:
        self._loading_overlay.show_overlay("正在生成本章摘要...")
        self._save_ark_settings()

        config = OpenClawConfig(
            api_key=self.ark_api_key_edit.text().strip(),
            base_url=os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").strip(),
            model=self.ark_model_edit.text().strip(),
            enable_web_search=False,
        )

        order = len(self._novel.chapters) + 1
        title = self.chapter_hint_edit.text().strip() or f"第{order}章"
        ch = Chapter(
            id=str(uuid.uuid4()),
            order=order,
            title=title,
            content=content,
            summary="",
        )
        self._novel.chapters.append(ch)
        self.content_edit.setPlainText(content)
        self.chapter_hint_edit.clear()
        self._refresh_chapter_list()
        self._suppress_chapter_save = True
        self.chapter_list.setCurrentRow(len(self._novel.chapters) - 1)

        # 异步生成摘要
        self._summary_worker = SummaryWorker(content, config, parent=self)
        self._summary_worker.finished.connect(lambda s: self._on_summary_done(ch, s))
        self._summary_worker.failed.connect(self._on_summary_failed)
        self._summary_worker.start()

    def _on_summary_done(self, ch: Chapter, summary: str) -> None:
        ch.summary = summary
        save_novel(self._novel)
        self._loading_overlay.hide_overlay()
        self.generate_btn.setEnabled(True)

    def _on_summary_failed(self, msg: str) -> None:
        self._loading_overlay.hide_overlay()
        self.generate_btn.setEnabled(True)
        QMessageBox.warning(self, "摘要生成失败", f"本章摘要未自动生成：{msg}\n可手动编辑。")

    def _on_chapter_failed(self, msg: str) -> None:
        self._loading_overlay.hide_overlay()
        self.generate_btn.setEnabled(True)
        QMessageBox.critical(self, "生成失败", f"调用模型失败：\n{msg}")

    def _save_ark_settings(self) -> None:
        self._settings.setValue("ark/api_key", self.ark_api_key_edit.text().strip())
        self._settings.setValue("ark/model", self.ark_model_edit.text().strip())
        self._settings.setValue(
            "ark/enable_web_search",
            "1" if self.enable_web_search_checkbox.isChecked() else "0",
        )

    def _export_markdown(self) -> None:
        if not self._novel:
            QMessageBox.warning(self, "提示", "请先选择一本小说。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出为 Markdown",
            f"{self._novel.title}.md",
            "Markdown (*.md);;所有文件 (*)",
        )
        if not path:
            return
        lines = [f"# {self._novel.title}\n"]
        for ch in self._novel.chapters:
            lines.append(f"\n## {ch.title or f'第{ch.order}章'}\n\n")
            lines.append(ch.content)
            lines.append("\n")
        Path(path).write_text("".join(lines), encoding="utf-8")
        QMessageBox.information(self, "导出成功", f"已导出到：{path}")


def main() -> None:
    app = QApplication([])
    win = MainWindow()
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
