from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional, Any, Dict

import requests
from PySide6.QtCore import QEvent, QRectF, QSettings, QTimer, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QFontMetrics, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import QGraphicsDropShadowEffect
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QInputDialog,
    QScrollArea,
    QWidget,
    QVBoxLayout,
)

from .collapsible_box import CollapsibleBox
from .config import load_config, OpenClawConfig
from .generator import ArticleGenerator, ArticleLength, WritingMode
from .prompt_templates import build_article_system_prompt_presets


class LoadingSpinner(QWidget):
    """渐变色圆弧旋转动画，带尾迹渐隐效果"""

    def __init__(self, size: int = 56, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._size = size
        self._angle = 0
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60fps

    def _tick(self) -> None:
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event: QEvent) -> None:
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._size
        pad = 5
        rect = QRectF(pad, pad, s - pad * 2, s - pad * 2)

        # 圆形背景（与卡片颜色一致，消除突兀感）
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QColor(99, 102, 241, 230))
        qp.drawEllipse(rect)

        # 背景圆环（白色低透明度轨道）
        pen = QPen(QColor(255, 255, 255, 50), 5, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        qp.setPen(pen)
        qp.drawArc(rect.toRect(), 0, 360 * 16)

        # 渐变色尾迹弧：从透明→白色，弧长270°
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
    """三点轮流高亮跳动"""

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


class PromptSlotItem(QWidget):
    activated = Signal(int)
    rename_requested = Signal(int)

    def __init__(self, index: int, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._index = index
        self._full_text = text
        self.setFixedSize(102, 32)

        self._button = QPushButton(self)
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.clicked.connect(lambda: self.activated.emit(self._index))

        self._edit_button = QPushButton("✎", self._button)
        self._edit_button.setFixedSize(18, 18)
        self._edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_button.setToolTip("编辑名称")
        self._edit_button.clicked.connect(lambda: self.rename_requested.emit(self._index))

        self.set_text(text)
        self.set_active(False)

    def set_text(self, text: str) -> None:
        self._full_text = text
        metrics = QFontMetrics(self._button.font())
        elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, 62)
        self._button.setText(elided)
        self._button.setToolTip(text)

    def set_active(self, active: bool) -> None:
        if active:
            self._button.setStyleSheet(
                "QPushButton {"
                "  background-color: #eef2ff;"
                "  color: #4338ca;"
                "  border: 1px solid #6366f1;"
                "  border-radius: 6px;"
                "  padding: 6px 24px 6px 8px;"
                "  font-size: 12px;"
                "  font-weight: 600;"
                "  text-align: left;"
                "}"
            )
        else:
            self._button.setStyleSheet(
                "QPushButton {"
                "  background-color: #ffffff;"
                "  color: #6b7280;"
                "  border: 1px solid #d1d5db;"
                "  border-radius: 6px;"
                "  padding: 6px 24px 6px 8px;"
                "  font-size: 12px;"
                "  font-weight: 500;"
                "  text-align: left;"
                "}"
                "QPushButton:hover {"
                "  border-color: #a5b4fc;"
                "  color: #4338ca;"
                "}"
            )

        self._edit_button.setStyleSheet(
            "QPushButton {"
            "  background-color: transparent;"
            "  color: #6b7280;"
            "  border: none;"
            "  border-radius: 4px;"
            "  padding: 0px;"
            "  font-size: 11px;"
            "}"
            "QPushButton:hover {"
            "  background-color: rgba(99, 102, 241, 0.10);"
            "  color: #4338ca;"
            "}"
        )

    def resizeEvent(self, event) -> None:
        self._button.setGeometry(0, 0, self.width(), self.height())
        self._edit_button.move(self.width() - self._edit_button.width() - 8, 7)
        super().resizeEvent(event)


class ChevronComboBox(QComboBox):
    """使用代码绘制下拉箭头，避免不同平台样式渲染异常。"""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor("#4338ca") if self.hasFocus() else QColor("#4b5563")
        pen = QPen(color, 1.8, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        center_x = self.width() - 18
        center_y = self.height() / 2 + 0.5
        half_width = 4.5
        half_height = 2.5

        path = QPainterPath()
        path.moveTo(center_x - half_width, center_y - half_height)
        path.lineTo(center_x, center_y + half_height)
        path.lineTo(center_x + half_width, center_y - half_height)
        painter.drawPath(path)


class LoadingOverlay(QWidget):
    """现代感半透明遮罩 + 居中加载卡片，支持淡入/淡出"""

    def __init__(self, parent: QWidget, message: str = "加载中") -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setWindowOpacity(0.0)
        self.hide()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 卡片：深色毛玻璃风格
        card = QFrame(self)
        card.setObjectName("LoadingCard")
        card.setStyleSheet("""
            #LoadingCard {
                background-color: rgba(99, 102, 241, 230);
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.3);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            }
        """)
        card.setMinimumWidth(220)
        card.setMaximumWidth(320)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(36, 28, 36, 28)
        card_layout.setSpacing(20)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._spinner = LoadingSpinner(56, card)
        card_layout.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignHCenter)

        self._label = _DotLabel(card)
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setStyleSheet(
            "color: rgba(230,230,230,220); font-size: 14px; font-weight: 500;"
        )
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.set_base(message)
        card_layout.addWidget(self._label, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addWidget(card)

        # 用 QGraphicsOpacityEffect 做淡入/淡出（对子 widget 有效）
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
        """绘制半透明深色遮罩背景"""
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


class GenerateWorker(QThread):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        topic: str,
        audience: Optional[str],
        style: Optional[str],
        length: ArticleLength,
        mode: WritingMode,
        system_prompt: Optional[str],
        creation_mode: str,
        source_article: Optional[str],
        rewrite_goal: str,
        reference_focus: str,
        reference_level: str,
        expression_mode: str,
        config_override: Optional[OpenClawConfig] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._topic = topic
        self._audience = audience
        self._style = style
        self._length = length
        self._mode = mode
        self._system_prompt = system_prompt
        self._creation_mode = creation_mode
        self._source_article = source_article
        self._rewrite_goal = rewrite_goal
        self._reference_focus = reference_focus
        self._reference_level = reference_level
        self._expression_mode = expression_mode
        self._config_override = config_override

    def run(self) -> None:
        try:
            config = self._config_override or load_config()
            generator = ArticleGenerator(config)
            content = generator.generate(
                topic=self._topic,
                audience=self._audience,
                style=self._style,
                length=self._length,
                mode=self._mode,
                system_prompt=self._system_prompt,
                creation_mode=self._creation_mode,
                source_article=self._source_article,
                rewrite_goal=self._rewrite_goal,
                reference_focus=self._reference_focus,
                reference_level=self._reference_level,
                expression_mode=self._expression_mode,
            )
            self.finished.emit(content)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OpenClaw - 公众号写作助手")

        # 设置固定窗口大小（不使用之前保存的大小）
        self.setFixedSize(1260, 780)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f7fa;
            }
            QGroupBox {
                background-color: white;
                border: 1px solid #e4e7eb;
                border-radius: 8px;
                padding: 4px;
                margin-top: 0px;
            }
            QLabel {
                color: #1f2937;
            }
            QLineEdit {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 8px 12px;
                background-color: white;
                color: #111827;
                font-size: 13px;
                selection-background-color: #e0e7ff;
                selection-color: #1f2937;
            }
            QLineEdit:hover {
                border-color: #9ca3af;
            }
            QLineEdit:focus {
                border: 1px solid #6366f1;
            }
            QComboBox {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 8px 12px;
                padding-right: 30px;
                background-color: white;
                color: #111827;
                font-size: 13px;
                selection-background-color: #e0e7ff;
                selection-color: #1f2937;
            }
            QComboBox:hover {
                border-color: #9ca3af;
            }
            QComboBox:focus {
                border: 1px solid #6366f1;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 30px;
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                width: 0px;
                height: 0px;
                border: none;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #c7d2fe;
                border-radius: 6px;
                background-color: #eef2ff;
                color: #111827;
                outline: none;
                padding: 0px;
                selection-background-color: #6366f1;
                selection-color: white;
            }
            QComboBox QAbstractItemView::item {
                padding: 8px 12px;
                border-radius: 0px;
                margin: 0px;
                min-height: 22px;
                background-color: #eef2ff;
                color: #111827;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #c7d2fe;
                color: #111827;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #6366f1;
                color: white;
            }
            QScrollBar:vertical {
                border: none;
                background-color: #f9fafb;
                width: 8px;
                border-radius: 4px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #d1d5db;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #9ca3af;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QPlainTextEdit {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 8px;
                background-color: white;
                color: #111827;
                font-size: 13px;
                selection-background-color: #e0e7ff;
                selection-color: #1f2937;
            }
            QPlainTextEdit:hover {
                border-color: #9ca3af;
            }
            QPlainTextEdit:focus {
                border: 1px solid #6366f1;
            }
            QPushButton {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 8px 16px;
                background-color: white;
                font-size: 13px;
                color: #374151;
            }
            QPushButton:hover {
                background-color: #f3f4f6;
                border-color: #6366f1;
                color: #1f2937;
            }
            QPushButton:pressed {
                background-color: #e5e7eb;
            }
            QPushButton:disabled {
                background-color: #f9fafb;
                color: #d1d5db;
                border-color: #e5e7eb;
            }
        """)

        # 本地配置持久化（豆包 / 公众号账号信息）
        self._settings = QSettings("OpenClaw", "WeChatWriter")

        self._worker: Optional[GenerateWorker] = None
        self._last_topic: str = ""
        self._wechat_accounts = self._load_wechat_accounts()
        self._active_wechat_account_index = self._load_active_wechat_account_index()
        self._prompt_slot_labels = ["提示词1", "提示词2", "提示词3", "提示词4"]
        self._prompt_slot_names = self._load_prompt_slot_names()
        self._prompt_slot_defaults = build_article_system_prompt_presets()
        self._prompt_slot_values = self._load_prompt_slot_values()
        self._active_prompt_slot = self._load_active_prompt_slot()
        self._prompt_slot_items: list[PromptSlotItem] = []
        self._is_switching_prompt_slot = False

        self._build_ui()
        self._build_menu()

    def _save_account_settings(self) -> None:
        """将豆包 / 公众号账号配置保存到本地。"""
        self._settings.setValue("ark/api_key", self.ark_api_key_edit.text().strip())
        self._settings.setValue("ark/model", self.ark_model_edit.text().strip())
        self._settings.setValue(
            "ark/enable_web_search",
            "1" if self.enable_web_search_checkbox.isChecked() else "0",
        )
        self._update_current_wechat_account_from_inputs()
        current_account = self._current_wechat_account()
        self._settings.setValue("wechat/appid", current_account["appid"])
        self._settings.setValue("wechat/appsecret", current_account["appsecret"])
        self._settings.setValue("wechat/thumb_media_id", current_account["thumb_media_id"])
        self._settings.setValue(
            "wechat/accounts_json",
            json.dumps(self._wechat_accounts, ensure_ascii=False),
        )
        self._settings.setValue(
            "wechat/active_account_index",
            self._active_wechat_account_index,
        )
        self._settings.sync()

    def _default_wechat_account(self, name: str = "公众号1") -> dict[str, str]:
        return {
            "name": name,
            "appid": "",
            "appsecret": "",
            "thumb_media_id": "",
        }

    def _coerce_wechat_account(
        self,
        raw: Any,
        fallback_name: str,
    ) -> dict[str, str]:
        if not isinstance(raw, dict):
            return self._default_wechat_account(fallback_name)
        return {
            "name": str(raw.get("name", fallback_name) or fallback_name).strip(),
            "appid": str(raw.get("appid", "") or "").strip(),
            "appsecret": str(raw.get("appsecret", "") or "").strip(),
            "thumb_media_id": str(raw.get("thumb_media_id", "") or "").strip(),
        }

    def _load_wechat_accounts(self) -> list[dict[str, str]]:
        raw_json = str(self._settings.value("wechat/accounts_json", "") or "").strip()
        accounts: list[dict[str, str]] = []
        if raw_json:
            try:
                parsed = json.loads(raw_json)
            except json.JSONDecodeError:
                parsed = []
            if isinstance(parsed, list):
                for index, raw in enumerate(parsed, start=1):
                    accounts.append(
                        self._coerce_wechat_account(raw, f"公众号{index}")
                    )
        if accounts:
            return accounts

        appid = str(self._settings.value("wechat/appid", os.getenv("WECHAT_APPID", "")) or "").strip()
        appsecret = str(
            self._settings.value("wechat/appsecret", os.getenv("WECHAT_APPSECRET", "")) or ""
        ).strip()
        thumb_media_id = str(
            self._settings.value(
                "wechat/thumb_media_id",
                os.getenv("WECHAT_THUMB_MEDIA_ID", ""),
            )
            or ""
        ).strip()
        if appid or appsecret or thumb_media_id:
            account = self._default_wechat_account("公众号1")
            account["appid"] = appid
            account["appsecret"] = appsecret
            account["thumb_media_id"] = thumb_media_id
            return [account]
        return [self._default_wechat_account("公众号1")]

    def _load_active_wechat_account_index(self) -> int:
        raw_value = self._settings.value("wechat/active_account_index", 0)
        try:
            index = int(raw_value)
        except (TypeError, ValueError):
            index = 0
        return max(0, min(index, len(self._wechat_accounts) - 1))

    def _current_wechat_account(self) -> dict[str, str]:
        return self._wechat_accounts[self._active_wechat_account_index]

    def _update_current_wechat_account_from_inputs(self) -> None:
        if not hasattr(self, "wechat_appid_edit"):
            return
        account = self._current_wechat_account()
        account["appid"] = self.wechat_appid_edit.text().strip()
        account["appsecret"] = self.wechat_appsecret_edit.text().strip()
        account["thumb_media_id"] = self.wechat_thumb_media_id_edit.text().strip()

    def _apply_current_wechat_account_to_inputs(self) -> None:
        if not hasattr(self, "wechat_appid_edit"):
            return
        account = self._current_wechat_account()
        self.wechat_appid_edit.setText(account["appid"])
        self.wechat_appsecret_edit.setText(account["appsecret"])
        self.wechat_thumb_media_id_edit.setText(account["thumb_media_id"])

    def _refresh_wechat_account_combo(self) -> None:
        if not hasattr(self, "wechat_account_combo"):
            return
        self.wechat_account_combo.blockSignals(True)
        self.wechat_account_combo.clear()
        for index, account in enumerate(self._wechat_accounts, start=1):
            self.wechat_account_combo.addItem(
                account["name"] or f"公众号{index}",
                index - 1,
            )
        self.wechat_account_combo.setCurrentIndex(self._active_wechat_account_index)
        self.wechat_account_combo.blockSignals(False)
        if hasattr(self, "wechat_delete_account_button"):
            self.wechat_delete_account_button.setEnabled(len(self._wechat_accounts) > 1)

    def _switch_wechat_account(self, index: int) -> None:
        if index < 0 or index >= len(self._wechat_accounts):
            return
        self._update_current_wechat_account_from_inputs()
        self._active_wechat_account_index = index
        self._apply_current_wechat_account_to_inputs()
        self._refresh_wechat_account_combo()
        self._save_account_settings()

    def _add_wechat_account(self) -> None:
        default_name = f"公众号{len(self._wechat_accounts) + 1}"
        name, ok = QInputDialog.getText(
            self,
            "新增公众号账号",
            "账号名称：",
            text=default_name,
        )
        if not ok:
            return
        self._update_current_wechat_account_from_inputs()
        self._wechat_accounts.append(
            self._default_wechat_account(name.strip() or default_name)
        )
        self._active_wechat_account_index = len(self._wechat_accounts) - 1
        self._apply_current_wechat_account_to_inputs()
        self._refresh_wechat_account_combo()
        self._save_account_settings()

    def _rename_wechat_account(self) -> None:
        account = self._current_wechat_account()
        default_name = f"公众号{self._active_wechat_account_index + 1}"
        name, ok = QInputDialog.getText(
            self,
            "编辑公众号账号",
            "账号名称：",
            text=account["name"] or default_name,
        )
        if not ok:
            return
        account["name"] = name.strip() or default_name
        self._refresh_wechat_account_combo()
        self._save_account_settings()

    def _delete_wechat_account(self) -> None:
        if len(self._wechat_accounts) <= 1:
            QMessageBox.information(self, "提示", "至少保留一个公众号账号。")
            return
        account_name = self._current_wechat_account()["name"] or "当前账号"
        reply = QMessageBox.question(
            self,
            "删除公众号账号",
            f"确认删除“{account_name}”吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._update_current_wechat_account_from_inputs()
        self._wechat_accounts.pop(self._active_wechat_account_index)
        self._active_wechat_account_index = min(
            self._active_wechat_account_index,
            len(self._wechat_accounts) - 1,
        )
        self._apply_current_wechat_account_to_inputs()
        self._refresh_wechat_account_combo()
        self._save_account_settings()

    def _load_prompt_slot_values(self) -> list[str]:
        values: list[str] = []
        for index, default_prompt in enumerate(self._prompt_slot_defaults):
            value = self._settings.value(f"prompts/slot_{index}", default_prompt)
            values.append(str(value) if value is not None else default_prompt)
        return values

    def _load_prompt_slot_names(self) -> list[str]:
        names: list[str] = []
        for index, default_name in enumerate(self._prompt_slot_labels):
            value = self._settings.value(f"prompts/name_{index}", default_name)
            text = str(value).strip() if value is not None else default_name
            names.append(text or default_name)
        return names

    def _load_active_prompt_slot(self) -> int:
        raw_value = self._settings.value("prompts/active_slot", 0)
        try:
            index = int(raw_value)
        except (TypeError, ValueError):
            index = 0
        return max(0, min(index, len(self._prompt_slot_labels) - 1))

    def _save_current_prompt_slot(self) -> None:
        if not hasattr(self, "prompt_edit"):
            return
        current_text = self.prompt_edit.toPlainText()
        self._prompt_slot_values[self._active_prompt_slot] = current_text
        self._settings.setValue(
            f"prompts/slot_{self._active_prompt_slot}",
            current_text,
        )

    def _save_current_prompt_name(self) -> None:
        default_name = self._prompt_slot_labels[self._active_prompt_slot]
        current_name = self._prompt_slot_names[self._active_prompt_slot].strip() or default_name
        self._prompt_slot_names[self._active_prompt_slot] = current_name
        self._settings.setValue(
            f"prompts/name_{self._active_prompt_slot}",
            current_name,
        )

    def _refresh_prompt_slot_buttons(self) -> None:
        for index, item in enumerate(self._prompt_slot_items):
            item.set_text(self._prompt_slot_names[index])
            item.set_active(index == self._active_prompt_slot)

    def _on_prompt_text_changed(self) -> None:
        if self._is_switching_prompt_slot:
            return
        self._save_current_prompt_slot()

    def _edit_prompt_slot_name(self, index: int) -> None:
        current_name = self._prompt_slot_names[index]
        default_name = self._prompt_slot_labels[index]
        new_name, ok = QInputDialog.getText(
            self,
            "编辑提示词名称",
            "名称：",
            text=current_name,
        )
        if not ok:
            return
        final_name = new_name.strip() or default_name
        self._prompt_slot_names[index] = final_name
        self._settings.setValue(f"prompts/name_{index}", final_name)
        self._refresh_prompt_slot_buttons()

    def _set_active_prompt_slot(self, index: int) -> None:
        if index < 0 or index >= len(self._prompt_slot_labels):
            return
        if hasattr(self, "prompt_edit"):
            self._save_current_prompt_slot()
        self._active_prompt_slot = index
        self._settings.setValue("prompts/active_slot", index)
        if hasattr(self, "prompt_edit"):
            self._is_switching_prompt_slot = True
            self.prompt_edit.setPlainText(self._prompt_slot_values[index])
            self._is_switching_prompt_slot = False
        self._refresh_prompt_slot_buttons()

    def _save_prompt_settings(self) -> None:
        self._save_current_prompt_slot()
        self._save_current_prompt_name()
        self._settings.setValue("prompts/active_slot", self._active_prompt_slot)
        for index, value in enumerate(self._prompt_slot_values):
            self._settings.setValue(f"prompts/slot_{index}", value)
        for index, name in enumerate(self._prompt_slot_names):
            self._settings.setValue(f"prompts/name_{index}", name)
        self._settings.sync()

    @staticmethod
    def _set_combo_current_data(combo: QComboBox, target: str) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == target:
                combo.setCurrentIndex(index)
                return

    def _save_article_settings(self) -> None:
        if not hasattr(self, "creation_mode_combo"):
            return
        self._settings.setValue(
            "article/rewrite_goal",
            self.rewrite_goal_combo.currentData() or "new_article",
        )
        self._settings.setValue(
            "article/reference_focus",
            self.reference_focus_combo.currentData() or "mixed",
        )
        self._settings.setValue(
            "article/reference_level",
            self.reference_level_combo.currentData() or "medium",
        )
        self._settings.setValue(
            "article/expression_mode",
            self.expression_mode_combo.currentData() or "standard",
        )
        self._settings.sync()

    def _default_generate_button_text(self) -> str:
        if not hasattr(self, "creation_mode_combo"):
            return "✨ 生成文章"
        return (
            "✨ 参考改写"
            if (self.creation_mode_combo.currentData() or "original") == "rewrite"
            else "✨ 生成文章"
        )

    def _update_creation_mode_ui(self) -> None:
        if not hasattr(self, "creation_mode_combo"):
            return
        is_rewrite = (self.creation_mode_combo.currentData() or "original") == "rewrite"
        for widget in (
            self.rewrite_goal_label,
            self.rewrite_goal_combo,
            self.reference_focus_label,
            self.reference_focus_combo,
            self.reference_level_label,
            self.reference_level_combo,
            self.reference_article_panel,
        ):
            widget.setVisible(is_rewrite)

        if is_rewrite:
            self.topic_edit.setPlaceholderText("选填：不填则沿用参考文章主题")
            self.reference_article_edit.setMinimumHeight(220)
            self.prompt_edit.setMinimumHeight(170)
            self.result_edit.setMinimumHeight(320)
        else:
            self.topic_edit.setPlaceholderText("必填")
            self.prompt_edit.setMinimumHeight(140)
            self.result_edit.setMinimumHeight(240)

        if hasattr(self, "right_scroll"):
            self.right_scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
                if is_rewrite
                else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            self.right_scroll.verticalScrollBar().setEnabled(is_rewrite)
            if not is_rewrite:
                self.right_scroll.verticalScrollBar().setValue(0)

        if hasattr(self, "generate_button") and (
            self._worker is None or not self._worker.isRunning()
        ):
            self.generate_button.setText(self._default_generate_button_text())

        self._save_article_settings()

    def _paste_source_article_from_clipboard(self) -> None:
        text = QApplication.clipboard().text().strip()
        if not text:
            QMessageBox.information(self, "提示", "剪贴板里没有可粘贴的文章内容。")
            return
        self.reference_article_edit.setPlainText(text)

    def _clear_source_article(self) -> None:
        self.reference_article_edit.clear()

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        self._central_widget = central

        left_col = QVBoxLayout()
        left_col.setContentsMargins(12, 12, 12, 12)
        left_col.setSpacing(12)

        # ── 账号配置折叠面板 ──────────────────────────
        config_box = CollapsibleBox("账号配置")

        def field_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                "color: #6b7280; font-size: 12px; font-weight: 500;"
                "background: transparent; border: none;"
            )
            return lbl

        self.ark_api_key_edit = QLineEdit()
        self.ark_api_key_edit.setEchoMode(QLineEdit.Password)
        self.ark_api_key_edit.setPlaceholderText("请输入")
        self.ark_model_edit = QLineEdit()
        self.ark_model_edit.setPlaceholderText("请输入")
        self.enable_web_search_checkbox = QCheckBox("🌐 联网生成")
        self.enable_web_search_checkbox.setStyleSheet("QCheckBox { font-size: 16px; }")
        self.enable_web_search_checkbox.setToolTip(
            "开启后模型可联网搜索最新信息辅助写作\n需要在火山引擎控制台开通 web_search 能力"
        )
        # 选中时显示对勾，优化文字与图标间距
        _check_svg = (
            "data:image/svg+xml;base64,"
            "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNiAxNiI+"
            "PHBhdGggZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2Ut"
            "bGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiIGQ9Ik0zIDhsMyAzIDctNyIv"
            "Pjwvc3ZnPg=="
        )
        self.enable_web_search_checkbox.setStyleSheet(
            "QCheckBox {"
            "  color: #6b7280; font-size: 13px; font-weight: 500;"
            "  background: transparent; border: none;"
            "  spacing: 10px;"
            "}"
            "QCheckBox::indicator {"
            "  width: 18px; height: 18px; border-radius: 4px;"
            "  border: 1px solid #d1d5db;"
            "  background-color: white;"
            "}"
            "QCheckBox::indicator:checked {"
            "  background-color: #6366f1; border-color: #6366f1;"
            f"  image: url({_check_svg});"
            "}"
        )
        self.wechat_account_combo = ChevronComboBox()
        self.wechat_account_combo.setToolTip("选择当前生效的公众号账号")
        self.wechat_add_account_button = QPushButton("新增")
        self.wechat_rename_account_button = QPushButton("编辑")
        self.wechat_delete_account_button = QPushButton("删除")
        self.wechat_appid_edit = QLineEdit()
        self.wechat_appid_edit.setPlaceholderText("请输入")
        self.wechat_appsecret_edit = QLineEdit()
        self.wechat_appsecret_edit.setEchoMode(QLineEdit.Password)
        self.wechat_appsecret_edit.setPlaceholderText("请输入")
        self.wechat_thumb_media_id_edit = QLineEdit()
        self.wechat_thumb_media_id_edit.setPlaceholderText("封面图 ID")

        # 优先读取本地配置，其次回退到环境变量
        self.ark_api_key_edit.setText(
            self._settings.value("ark/api_key", os.getenv("ARK_API_KEY", ""))
        )
        self.ark_model_edit.setText(
            self._settings.value("ark/model", os.getenv("ARK_MODEL", ""))
        )
        self._apply_current_wechat_account_to_inputs()
        self._refresh_wechat_account_combo()
        # 联网开关：本地优先，其次回退到环境变量 ARK_ENABLE_WEB_SEARCH
        enable_web_search_default = os.getenv("ARK_ENABLE_WEB_SEARCH", "0").strip()
        enable_web_search_flag = enable_web_search_default.lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        enable_web_search_value = self._settings.value(
            "ark/enable_web_search", "1" if enable_web_search_flag else "0"
        )
        self.enable_web_search_checkbox.setChecked(
            str(enable_web_search_value).lower() in {"1", "true", "yes", "on"}
        )
        for button in (
            self.wechat_add_account_button,
            self.wechat_rename_account_button,
            self.wechat_delete_account_button,
        ):
            button.setStyleSheet(
                "QPushButton {"
                "  padding: 6px 10px;"
                "  font-size: 12px;"
                "}"
            )
        self.wechat_account_combo.currentIndexChanged.connect(self._switch_wechat_account)
        self.wechat_add_account_button.clicked.connect(self._add_wechat_account)
        self.wechat_rename_account_button.clicked.connect(self._rename_wechat_account)
        self.wechat_delete_account_button.clicked.connect(self._delete_wechat_account)
        self.wechat_appid_edit.editingFinished.connect(self._save_account_settings)
        self.wechat_appsecret_edit.editingFinished.connect(self._save_account_settings)
        self.wechat_thumb_media_id_edit.editingFinished.connect(self._save_account_settings)

        self.upload_thumb_button = QPushButton("📁 上传图片")
        self.upload_thumb_button.setToolTip(
            "PNG → type=thumb（≤64KB）\nJPG → type=image（≤10MB）\n上传后自动填入 thumb_media_id"
        )
        self.upload_thumb_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #f0f9ff; color: #0369a1;"
            "  border: 1px solid #bae6fd; border-radius: 6px;"
            "  padding: 6px 14px; font-size: 13px;"
            "}"
            "QPushButton:hover { background-color: #e0f2fe; border-color: #7dd3fc; }"
            "QPushButton:pressed { background-color: #bae6fd; }"
        )
        self.upload_thumb_button.clicked.connect(self._on_upload_thumb_clicked)

        thumb_hint = QLabel("支持 PNG/JPG，自动识别格式")
        thumb_hint.setStyleSheet(
            "color: #9ca3af; font-size: 11px; background: transparent; border: none;"
        )

        for lbl_text, widget in [
            ("豆包 Key", self.ark_api_key_edit),
            ("豆包模型", self.ark_model_edit),
        ]:
            config_box.add_widget(field_label(lbl_text))
            config_box.add_widget(widget)
        config_box.add_widget(field_label("公众号账号"))
        account_row_top = QWidget()
        account_row_top_layout = QHBoxLayout(account_row_top)
        account_row_top_layout.setContentsMargins(0, 0, 0, 0)
        account_row_top_layout.setSpacing(6)
        account_row_top_layout.addWidget(self.wechat_account_combo, 1)
        account_row_top_layout.addWidget(self.wechat_add_account_button)
        account_row_top_layout.addWidget(self.wechat_rename_account_button)
        account_row_top_layout.addWidget(self.wechat_delete_account_button)
        config_box.add_widget(account_row_top)
        for lbl_text, widget in [
            ("公众号 AppID", self.wechat_appid_edit),
            ("公众号 Secret", self.wechat_appsecret_edit),
        ]:
            config_box.add_widget(field_label(lbl_text))
            config_box.add_widget(widget)

        config_box.add_widget(field_label("封面图 thumb_media_id"))
        config_box.add_widget(self.upload_thumb_button)
        config_box.add_widget(self.wechat_thumb_media_id_edit)
        config_box.add_widget(thumb_hint)

        # ── 文章折叠面板 ──────────────────────────────
        article_box = CollapsibleBox("文章")

        self.creation_mode_combo = ChevronComboBox()
        self.creation_mode_combo.addItem("原创生成", "original")
        self.creation_mode_combo.addItem("参考改写", "rewrite")

        self.topic_edit = QLineEdit()
        self.topic_edit.setPlaceholderText("必填")

        self.audience_combo = ChevronComboBox()
        self.audience_combo.addItem("微信用户", "经常使用微信的普通用户")
        self.audience_combo.addItem("不指定", "")
        self.audience_combo.addItem("职场新人", "职场新人")
        self.audience_combo.addItem("互联网打工人", "互联网打工人")
        self.audience_combo.addItem("大学生", "大学生")
        self.audience_combo.addItem("普通宝妈", "宝妈/宝爸等家庭用户")
        self.audience_combo.addItem("小白用户", "几乎零基础的小白用户")
        self.audience_combo.addItem("中小企业老板", "中小企业老板或个体经营者")

        self.style_combo = ChevronComboBox()
        self.style_combo.addItem("不指定", "")
        self.style_combo.addItem("科普聊天", "通俗易懂、像跟朋友聊天一样的科普风格。")
        self.style_combo.addItem("职场干货", "结构清晰、观点明确、偏职场实战干货。")
        self.style_combo.addItem("故事分享", "通过个人故事或案例来讲道理，轻松、有画面感。")
        self.style_combo.addItem("运营拆解", "以拆解案例为主，有步骤、有数据、有总结。")

        self.length_combo = ChevronComboBox()
        self.length_combo.addItem("中等", "medium")
        self.length_combo.addItem("偏短", "short")
        self.length_combo.addItem("偏长", "long")

        self.mode_combo = ChevronComboBox()
        self.mode_combo.addItem("标准干货", "standard")
        self.mode_combo.addItem("故事化", "story")
        self.mode_combo.addItem("案例拆解", "case_study")
        self.mode_combo.addItem("清单文", "listicle")
        self.mode_combo.addItem("深度分析", "analysis")

        self.rewrite_goal_combo = ChevronComboBox()
        self.rewrite_goal_combo.addItem("生成新稿", "new_article")
        self.rewrite_goal_combo.addItem("换个角度写", "new_angle")
        self.rewrite_goal_combo.addItem("更口语一点", "more_conversational")
        self.rewrite_goal_combo.addItem("更干货一点", "more_actionable")

        self.reference_focus_combo = ChevronComboBox()
        self.reference_focus_combo.addItem("综合借鉴", "mixed")
        self.reference_focus_combo.addItem("借鉴结构", "structure")
        self.reference_focus_combo.addItem("借鉴语气", "tone")
        self.reference_focus_combo.addItem("借鉴开头切口", "opening")

        self.reference_level_combo = ChevronComboBox()
        self.reference_level_combo.addItem("低", "low")
        self.reference_level_combo.addItem("中", "medium")
        self.reference_level_combo.addItem("高", "high")

        self.expression_mode_combo = ChevronComboBox()
        self.expression_mode_combo.addItem("标准", "standard")
        self.expression_mode_combo.addItem("更口语", "conversational")
        self.expression_mode_combo.addItem("去AI味", "de_ai")
        self.expression_mode_combo.addItem("强观点", "opinionated")

        # 给所有下拉框的弹出视图加投影 + 背景色，产生层次感
        def _apply_combo_popup_style(combo: QComboBox) -> None:
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(18)
            shadow.setOffset(0, 4)
            shadow.setColor(QColor(0, 0, 0, 70))
            combo.view().setGraphicsEffect(shadow)
            # viewport 是实际可见区域，必须单独设置背景色
            combo.view().viewport().setStyleSheet(
                "background-color: #eef2ff;"
            )

        for _combo in (
            self.creation_mode_combo, self.audience_combo, self.style_combo,
            self.length_combo, self.mode_combo,
            self.rewrite_goal_combo, self.reference_focus_combo, self.reference_level_combo,
            self.expression_mode_combo,
        ):
            _apply_combo_popup_style(_combo)

        self.creation_mode_combo.setCurrentIndex(0)
        self._set_combo_current_data(
            self.rewrite_goal_combo,
            str(self._settings.value("article/rewrite_goal", "new_article") or "new_article"),
        )
        self._set_combo_current_data(
            self.reference_focus_combo,
            str(self._settings.value("article/reference_focus", "mixed") or "mixed"),
        )
        self._set_combo_current_data(
            self.reference_level_combo,
            str(self._settings.value("article/reference_level", "medium") or "medium"),
        )
        self._set_combo_current_data(
            self.expression_mode_combo,
            str(self._settings.value("article/expression_mode", "standard") or "standard"),
        )

        self.generate_button = QPushButton("✨ 生成文章")
        self.generate_button.setMinimumHeight(40)
        self.generate_button.setMinimumWidth(120)
        self.generate_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #667eea; color: #ffffff;"
            "  font-weight: 600; padding: 10px 28px;"
            "  border: none; border-radius: 8px; font-size: 15px;"
            "}"
            "QPushButton:hover { background-color: #5568d3; }"
            "QPushButton:pressed { background-color: #4c5bc7; }"
            "QPushButton:disabled { background-color: #e5e7eb; color: #9ca3af; }"
        )
        self.generate_button.clicked.connect(self._on_generate_clicked)

        # 用 Grid 布局排列标签和控件（标签靠左，控件拉伸）
        article_grid_widget = QWidget()
        article_grid_widget.setStyleSheet("background: transparent; border: none;")
        article_grid = QGridLayout(article_grid_widget)
        article_grid.setContentsMargins(0, 0, 0, 0)
        article_grid.setColumnStretch(1, 1)
        article_grid.setVerticalSpacing(8)
        article_grid.setHorizontalSpacing(10)

        article_rows = [
            ("创作方式", self.creation_mode_combo, "creation_mode_label"),
            ("主题", self.topic_edit, "topic_label"),
            ("读者", self.audience_combo, "audience_label"),
            ("风格", self.style_combo, "style_label"),
            ("表达处理", self.expression_mode_combo, "expression_mode_label"),
            ("长度", self.length_combo, "length_label"),
            ("模式", self.mode_combo, "mode_label"),
            ("改写目标", self.rewrite_goal_combo, "rewrite_goal_label"),
            ("借鉴维度", self.reference_focus_combo, "reference_focus_label"),
            ("参考程度", self.reference_level_combo, "reference_level_label"),
        ]

        for row, (lbl_text, widget, attr_name) in enumerate(article_rows):
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet(
                "color: #6b7280; font-size: 13px; font-weight: 500;"
                "background: transparent; border: none;"
            )
            setattr(self, attr_name, lbl)
            article_grid.addWidget(lbl, row, 0)
            article_grid.addWidget(widget, row, 1)

        # 联网开关放在最后一行，跨两列
        next_row = len(article_rows)
        article_grid.addWidget(self.enable_web_search_checkbox, next_row, 0, 1, 2)

        self.creation_mode_combo.currentIndexChanged.connect(self._update_creation_mode_ui)
        self.rewrite_goal_combo.currentIndexChanged.connect(self._save_article_settings)
        self.reference_focus_combo.currentIndexChanged.connect(self._save_article_settings)
        self.reference_level_combo.currentIndexChanged.connect(self._save_article_settings)
        self.expression_mode_combo.currentIndexChanged.connect(self._save_article_settings)

        article_box.add_widget(article_grid_widget)

        # 左侧整体顺序：先账号配置，再文章
        left_col.addWidget(config_box)
        left_col.addWidget(article_box)


        # 提示词编辑区（系统提示词）
        self.reference_article_panel = QWidget()
        self.reference_article_panel.setStyleSheet("background: transparent; border: none;")
        reference_layout = QVBoxLayout(self.reference_article_panel)
        reference_layout.setContentsMargins(0, 0, 0, 0)
        reference_layout.setSpacing(8)

        reference_header = QHBoxLayout()
        reference_header.setContentsMargins(0, 0, 0, 0)
        reference_header.setSpacing(8)
        reference_label = QLabel("🧷 参考文章")
        reference_label.setStyleSheet("font-size: 13px; color: #6b7280; font-weight: 500;")
        self.paste_source_button = QPushButton("粘贴")
        self.paste_source_button.setToolTip("从剪贴板粘贴参考文章")
        self.clear_source_button = QPushButton("清空")
        self.clear_source_button.setToolTip("清空参考文章内容")
        for button in (self.paste_source_button, self.clear_source_button):
            button.setStyleSheet(
                "QPushButton {"
                "  padding: 4px 12px;"
                "  font-size: 12px;"
                "  border-radius: 6px;"
                "}"
            )
        self.paste_source_button.clicked.connect(self._paste_source_article_from_clipboard)
        self.clear_source_button.clicked.connect(self._clear_source_article)
        reference_header.addWidget(reference_label)
        reference_header.addStretch(1)
        reference_header.addWidget(self.paste_source_button)
        reference_header.addWidget(self.clear_source_button)

        self.reference_article_edit = QPlainTextEdit()
        self.reference_article_edit.setPlaceholderText(
            "把要参考的爆款文章正文粘贴在这里。\n\n系统会重点借鉴结构、切口和表达节奏，生成一篇新的原创版本，而不是直接复述原文。"
        )
        self.reference_article_edit.setMinimumHeight(220)
        self.reference_article_edit.setStyleSheet(
            "QPlainTextEdit {"
            "  border: 1px solid #d1d5db;"
            "  border-radius: 6px;"
            "  background-color: #f9fafb;"
            "  color: #111827;"
            "  font-size: 12px;"
            "  padding: 10px;"
            "  line-height: 1.5;"
            "}"
        )

        reference_hint = QLabel("建议粘贴完整正文；不会默认长期保存这篇参考文章。")
        reference_hint.setStyleSheet(
            "color: #9ca3af; font-size: 11px; background: transparent; border: none;"
        )
        reference_layout.addLayout(reference_header)
        reference_layout.addWidget(self.reference_article_edit)
        reference_layout.addWidget(reference_hint)

        prompt_label = QLabel("💡 系统提示词")
        prompt_label.setStyleSheet("font-size: 13px; color: #6b7280; font-weight: 500;")
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText("可选：自定义写作风格与规则，留空则使用默认提示词")
        self.prompt_edit.setPlainText(self._prompt_slot_values[self._active_prompt_slot])
        self.prompt_edit.setMinimumHeight(170)
        self.prompt_edit.setStyleSheet(
            "QPlainTextEdit {"
            "  border: 1px solid #d1d5db;"
            "  border-radius: 6px;"
            "  background-color: #f9fafb;"
            "  color: #111827;"
            "  font-size: 12px;"
            "  padding: 10px;"
            "  line-height: 1.5;"
            "}"
        )

        # ---------- 右侧结果 ----------
        self.prompt_edit.textChanged.connect(self._on_prompt_text_changed)

        result_group = QGroupBox()
        result_group.setStyleSheet(
            "QGroupBox {"
            "  background-color: white;"
            "  border: 1px solid #e4e7eb;"
            "  border-radius: 8px;"
            "  padding: 20px;"
            "  margin-left: 0px;"
            "}"
        )
        result_layout = QVBoxLayout(result_group)
        result_layout.setSpacing(15)
        result_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel("生成结果")
        title_label.setStyleSheet(
            "font-weight: 600; font-size: 15px; color: #111827; margin-bottom: 8px;"
        )

        warn_label = QLabel(
            "⚠️ 注意：不理解 Markdown 格式的不要在此页面修改，"
            "发送到公众号后在草稿箱修改即可！"
        )
        warn_label.setStyleSheet(
            "color: #dc2626; font-size: 12px; background-color: #fef2f2; "
            "padding: 8px 12px; border-radius: 6px; border: 1px solid #fecaca;"
        )

        self.result_edit = QPlainTextEdit()
        self.result_edit.setPlaceholderText("生成后的 Markdown 显示在此。")
        self.result_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.result_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.result_edit.setMinimumHeight(320)
        self.result_edit.setStyleSheet(
            "QPlainTextEdit {"
            "  border: 1px solid #d1d5db;"
            "  border-radius: 6px;"
            "  background-color: #fafbfc;"
            "  color: #111827;"
            "  font-family: 'SF Mono', Consolas, Menlo, monospace;"
            "  font-size: 13px;"
            "  line-height: 1.6;"
            "  padding: 12px;"
            "}"
        )

        buttons_bar = QHBoxLayout()
        self.copy_button = QPushButton("📋 复制")
        self.copy_button.setStyleSheet(
            "QPushButton {"
            "  background-color: white;"
            "  color: #374151;"
            "  border: 1px solid #d1d5db;"
            "  border-radius: 6px;"
            "  padding: 3px 12px;"
            "  font-size: 13px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #f3f4f6;"
            "  border-color: #6366f1;"
            "}"
            "QPushButton:pressed {"
            "  background-color: #e5e7eb;"
            "}"
        )
        self.copy_button.clicked.connect(self._copy_result_to_clipboard)
        
        self.clear_button = QPushButton("🗑️ 清空")
        self.clear_button.setStyleSheet(
            "QPushButton {"
            "  background-color: white;"
            "  color: #dc2626;"
            "  border: 1px solid #fecaca;"
            "  border-radius: 6px;"
            "  padding: 3px 12px;"
            "  font-size: 13px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #fef2f2;"
            "  border-color: #dc2626;"
            "}"
            "QPushButton:pressed {"
            "  background-color: #fee2e2;"
            "}"
        )
        self.clear_button.clicked.connect(self._clear_result)
        self.send_wechat_button = QPushButton("📤 发到公众号草稿")
        self.send_wechat_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #10b981;"
            "  color: white;"
            "  border: none;"
            "  border-radius: 6px;"
            "  padding: 3px 12px;"
            "  font-size: 13px;"
            "  font-weight: 500;"
            "}"
            "QPushButton:hover {"
            "  background-color: #059669;"
            "}"
            "QPushButton:pressed {"
            "  background-color: #047857;"
            "}"
        )
        self.send_wechat_button.clicked.connect(self._send_to_wechat_draft)
        buttons_bar.addWidget(self.copy_button)
        buttons_bar.addWidget(self.clear_button)
        buttons_bar.addWidget(self.send_wechat_button)
        buttons_bar.addStretch(1)

        self.reset_prompt_button = QPushButton("🔄 重置")
        self.reset_prompt_button.setToolTip("恢复为默认系统提示词")
        self.reset_prompt_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #f3f4f6;"
            "  color: #374151;"
            "  border: 1px solid #d1d5db;"
            "  border-radius: 6px;"
            "  padding: 6px 14px;"
            "  font-size: 13px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #e5e7eb;"
            "  border-color: #9ca3af;"
            "}"
            "QPushButton:pressed {"
            "  background-color: #d1d5db;"
            "}"
        )
        for index, _ in enumerate(self._prompt_slot_labels):
            item = PromptSlotItem(index, self._prompt_slot_names[index])
            item.activated.connect(self._set_active_prompt_slot)
            item.rename_requested.connect(self._edit_prompt_slot_name)
            self._prompt_slot_items.append(item)
        self.reset_prompt_button.clicked.connect(self._on_reset_prompt_clicked)

        # 顶部操作栏：提示词标签 + 按钮组
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)
        top_bar.addWidget(prompt_label)
        for item in self._prompt_slot_items:
            top_bar.addWidget(item)
        top_bar.addStretch(1)
        top_bar.addWidget(self.reset_prompt_button)
        top_bar.addWidget(self.generate_button)
        self._refresh_prompt_slot_buttons()
        
        result_layout.addWidget(self.reference_article_panel)
        result_layout.addLayout(top_bar)
        result_layout.addWidget(self.prompt_edit)
        result_layout.addWidget(title_label)
        result_layout.addWidget(warn_label)
        result_layout.addWidget(self.result_edit)
        result_layout.addLayout(buttons_bar)
        self._update_creation_mode_ui()

        # 主区域：左侧 + 右侧（顶部对齐）
        main_v = QVBoxLayout(central)
        main_v.setContentsMargins(0, 0, 0, 0)
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(6, 4, 12, 6)
        top_layout.setSpacing(12)

        left_widget = QWidget()
        left_widget.setContentsMargins(0, 0, 0, 0)
        left_widget.setLayout(left_col)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFixedWidth(350)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        left_scroll.setWidget(left_widget)

        right_content = QWidget()
        right_content.setStyleSheet("background: transparent; border: none;")
        right_content_layout = QVBoxLayout(right_content)
        right_content_layout.setContentsMargins(0, 0, 0, 0)
        right_content_layout.setSpacing(0)
        right_content_layout.addWidget(result_group)

        self.right_scroll = QScrollArea()
        self.right_scroll.setWidgetResizable(True)
        self.right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.right_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self.right_scroll.setWidget(right_content)

        top_layout.addWidget(left_scroll, 0)
        top_layout.addWidget(self.right_scroll, 1)
        main_v.addWidget(top_widget, 1)

        # 水印：整窗底部，左右居中
        watermark = QLabel("✨ 关注微信公众号「不贴心小助手」，获取更多内容！")
        watermark.setStyleSheet(
            "color: #6366f1; font-size: 13px; font-weight: 500; "
            "padding: 2px 0; background-color: transparent;"
        )
        watermark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_v.addWidget(watermark, 0, Qt.AlignmentFlag.AlignHCenter)

        # 加载遮罩（生成文章时显示）
        self._loading_overlay = LoadingOverlay(central, "正在生成文章...")
        central.installEventFilter(self)

    def eventFilter(self, obj: QWidget, event: QEvent) -> bool:
        if obj is self._central_widget and event.type() == QEvent.Type.Resize:
            self._loading_overlay.setGeometry(self._central_widget.rect())
        return super().eventFilter(obj, event)

    def closeEvent(self, event) -> None:
        self._save_account_settings()
        self._save_article_settings()
        self._save_prompt_settings()
        super().closeEvent(event)

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件")
        save_action = QAction("保存为 Markdown...", self)
        save_action.triggered.connect(self._save_as_markdown)
        file_menu.addAction(save_action)

        help_menu = menubar.addMenu("帮助")
        about_action = QAction("关于 OpenClaw", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _on_reset_prompt_clicked(self) -> None:
        """恢复为默认系统提示词。"""
        default_prompt = self._prompt_slot_defaults[self._active_prompt_slot]
        self._prompt_slot_values[self._active_prompt_slot] = default_prompt
        self.prompt_edit.setPlainText(default_prompt)
        self._save_current_prompt_slot()

    def _on_generate_clicked(self) -> None:
        topic = self.topic_edit.text().strip()
        creation_mode = self.creation_mode_combo.currentData() or "original"
        source_article = self.reference_article_edit.toPlainText().strip() or None

        if creation_mode == "original" and not topic:
            QMessageBox.warning(self, "提示", "请先填写文章主题。")
            return
        if creation_mode == "rewrite":
            if not source_article:
                QMessageBox.warning(self, "提示", "请先粘贴一篇参考文章。")
                return
            if len(source_article) < 300:
                QMessageBox.warning(self, "提示", "参考文章内容太短了，建议至少粘贴 300 字以上的完整正文。")
                return

        audience = self.audience_combo.currentData() or None
        style = self.style_combo.currentData() or None
        length_value = self.length_combo.currentData()
        length: ArticleLength = length_value  # type: ignore[assignment]
        mode_value = self.mode_combo.currentData()
        mode: WritingMode = mode_value  # type: ignore[assignment]
        rewrite_goal = self.rewrite_goal_combo.currentData() or "new_article"
        reference_focus = self.reference_focus_combo.currentData() or "mixed"
        reference_level = self.reference_level_combo.currentData() or "medium"
        expression_mode = self.expression_mode_combo.currentData() or "standard"

        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "提示", "正在生成中，请稍候……")
            return

        system_prompt = self.prompt_edit.toPlainText().strip() or None

        # 保存当前账号配置，方便下次启动自动带出
        self._save_account_settings()
        self._save_article_settings()
        self._save_prompt_settings()

        self.generate_button.setEnabled(False)
        self.generate_button.setText("生成中...")
        self._loading_overlay.show_overlay(
            "正在参考改写..."
            if creation_mode == "rewrite"
            else "正在生成文章..."
        )

        # 记录最近一次生成使用的主题，后面作为公众号标题候选
        self._last_topic = topic

        # 若界面填写了豆包 Key 和模型，优先用界面配置（Base URL 固定用 .env 或默认）
        ark_key = self.ark_api_key_edit.text().strip()
        ark_model = self.ark_model_edit.text().strip()
        config_override: Optional[OpenClawConfig] = None
        if ark_key and ark_model:
            base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").strip()
            config_override = OpenClawConfig(
                api_key=ark_key,
                base_url=base_url,
                model=ark_model,
                enable_web_search=self.enable_web_search_checkbox.isChecked(),
            )

        self._worker = GenerateWorker(
            topic=topic,
            audience=audience,
            style=style,
            length=length,
            mode=mode,
            system_prompt=system_prompt,
            creation_mode=creation_mode,
            source_article=source_article,
            rewrite_goal=rewrite_goal,
            reference_focus=reference_focus,
            reference_level=reference_level,
            expression_mode=expression_mode,
            config_override=config_override,
            parent=self,
        )
        self._worker.finished.connect(self._on_generate_finished)
        self._worker.failed.connect(self._on_generate_failed)
        self._worker.start()

    def _on_generate_finished(self, content: str) -> None:
        self._loading_overlay.hide_overlay()
        self.generate_button.setEnabled(True)
        self.generate_button.setText(self._default_generate_button_text())
        self.result_edit.setPlainText(content)

    def _on_generate_failed(self, message: str) -> None:
        self._loading_overlay.hide_overlay()
        self.generate_button.setEnabled(True)
        self.generate_button.setText(self._default_generate_button_text())
        QMessageBox.critical(self, "生成失败", f"调用大模型失败：\n{message}")

    def _copy_result_to_clipboard(self) -> None:
        text = self.result_edit.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "提示", "当前没有可复制的内容。")
            return
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "已复制", "全文已复制到剪贴板，可以直接粘贴到公众号后台。")

    def _clear_result(self) -> None:
        self.result_edit.clear()

    def _on_upload_thumb_clicked(self) -> None:
        """通过后端服务上传封面图，根据格式自动选 type，自动填入 thumb_media_id。"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择封面图（PNG ≤64KB / JPG ≤10MB）",
            str(Path.home()),
            "封面图 (*.jpg *.jpeg *.png)",
        )
        if not filename:
            return

        # 根据扩展名判断上传类型（不再在客户端限制大小，交给微信接口自身校验）
        suffix = Path(filename).suffix.lower()
        if suffix == ".png":
            media_type = "thumb"          # PNG → type=thumb
            mime_type = "image/png"
        elif suffix in (".jpg", ".jpeg"):
            media_type = "image"          # JPG → type=image
            mime_type = "image/jpeg"
        else:
            QMessageBox.warning(
                self, "格式不支持",
                f"仅支持 PNG（≤64KB）和 JPG（≤10MB）。\n当前文件：{Path(filename).name}",
            )
            return

        # 更新本地保存的账号配置（便于下次自动填充）
        self._save_account_settings()

        self.upload_thumb_button.setEnabled(False)
        self.upload_thumb_button.setText("上传中...")
        self._loading_overlay.show_overlay("正在上传封面图")
        error_msg: Optional[str] = None
        thumb_id = ""
        try:
            with open(filename, "rb") as f:
                file_bytes = f.read()

            # 通过后端转发到微信接口
            backend_base = os.getenv(
                "BACKEND_BASE_URL", "http://49.235.172.63:8000/"
            ).rstrip("/")
            fname = Path(filename).name
            files = {"file": (fname, file_bytes, mime_type)}

            # 可选：将当前填写的 AppID/Secret 传给后端，未填写则由后端自己用环境变量
            appid = self.wechat_appid_edit.text().strip()
            appsecret = self.wechat_appsecret_edit.text().strip()
            form_data: Dict[str, str] = {}
            if appid and appsecret:
                form_data["wechat_appid"] = appid
                form_data["wechat_appsecret"] = appsecret

            resp = requests.post(
                f"{backend_base}/wechat/upload_thumb",
                data=form_data,
                files=files,
                timeout=60,
            )
            if resp.status_code != 200:
                error_msg = (
                    f"后端返回错误状态码 {resp.status_code}：\n{resp.text}"
                )
                return

            data = resp.json()
            thumb_id = data.get("thumb_media_id", "")
            if not thumb_id:
                error_msg = f"后端未返回 thumb_media_id：\n{data}"
                return

            self.wechat_thumb_media_id_edit.setText(thumb_id)
            self._save_account_settings()

        except Exception as exc:  # noqa: BLE001
            error_msg = f"上传时出错：\n{exc}"
        finally:
            # 先关闭 loading，再弹窗（避免 QMessageBox 阻塞动画）
            self._loading_overlay.hide_overlay()
            self.upload_thumb_button.setEnabled(True)
            if error_msg:
                self.upload_thumb_button.setText("📁 上传图片")
                QMessageBox.critical(self, "上传失败", error_msg)
            elif thumb_id:
                # 无弹窗，按钮短暂显示成功状态
                self.upload_thumb_button.setText("✅ 已填入")
                QTimer.singleShot(2000, lambda: self.upload_thumb_button.setText("📁 上传图片"))

    def _extract_title_from_markdown(self, text: str) -> str:
        # 1. 优先使用用户在左侧填写的「主题」
        if self._last_topic:
            base = self._last_topic.strip()
        else:
            base = ""

        # 2. 如果没有主题，再从 Markdown 中找第一个标题行
        if not base:
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("#"):
                    base = re.sub(r"^#+", "", line).strip()
                    break

        # 3. 还没有，就从全文提取前若干个字
        if not base:
            pure = re.sub(r"[\r\n#*`>-]", " ", text)
            pure = re.sub(r"\s+", " ", pure).strip()
            base = pure or "未命名文章"

        # 4. 为了避免触发公众号标题长度限制，统一截断到 20 个字符以内
        return base[:20]

    def _send_to_wechat_draft(self) -> None:
        text = self.result_edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "提示", "当前没有可发送的内容。")
            return

        backend_base = os.getenv("BACKEND_BASE_URL", "http://49.235.172.63:8000/").rstrip("/")
        title = self._extract_title_from_markdown(text)

         # 从界面读取（可选）公众号配置，未填写则让后端使用默认 .env
        wechat_appid = self.wechat_appid_edit.text().strip() or None
        wechat_appsecret = self.wechat_appsecret_edit.text().strip() or None
        wechat_thumb_media_id = self.wechat_thumb_media_id_edit.text().strip() or None

        payload = {
            "title": title,
            "content_md": text,
        }
        if wechat_appid and wechat_appsecret:
            payload["wechat_appid"] = wechat_appid
            payload["wechat_appsecret"] = wechat_appsecret
        if wechat_thumb_media_id:
            payload["wechat_thumb_media_id"] = wechat_thumb_media_id

        # 保存当前账号配置
        self._save_account_settings()

        self._loading_overlay.show_overlay("正在发送到公众号...")
        try:
            resp = requests.post(
                f"{backend_base}/wechat/draft",
                json=payload,
                timeout=20,
            )
            if resp.status_code != 200:
                QMessageBox.critical(
                    self,
                    "发送失败",
                    f"后端返回错误状态码 {resp.status_code}：\n{resp.text}",
                )
                return
            data = resp.json()
            draft_id = data.get("media_id", "")
            QMessageBox.information(
                self,
                "发送成功",
                f"已创建公众号草稿。\nmedia_id: {draft_id}\n请到公众号后台草稿箱查看。",
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                "发送失败",
                f"调用后端接口异常：\n{exc}\n\n"
                "请确认已在终端启动后端服务：\n"
                "uvicorn wechat_backend.app:app --reload",
            )
        finally:
            self._loading_overlay.hide_overlay()

    def _save_as_markdown(self) -> None:
        text = self.result_edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "提示", "当前没有可保存的内容。")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "保存为 Markdown 文件",
            str(Path.cwd() / "openclaw_article.md"),
            "Markdown 文件 (*.md);;所有文件 (*)",
        )
        if not filename:
            return

        try:
            Path(filename).write_text(text, encoding="utf-8")
            QMessageBox.information(self, "保存成功", f"已保存到：\n{filename}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", f"保存文件时出错：\n{exc}")

    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "关于 OpenClaw",
            "OpenClaw - 自动生成公众号文章初稿的小工具。\n\n"
            "适合作为写作前的「打底稿」，再由人类进行润色和改写。",
        )


def main() -> None:
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

