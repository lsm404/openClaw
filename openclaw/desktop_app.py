from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Optional

import requests
# from PySide6.QtCore import Qt, QThread, Signal
# from PySide6.QtGui import QAction
from PySide6.QtCore import QEvent, QRectF, QTimer, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
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
    QWidget,
    QVBoxLayout,
)

from .config import load_config, OpenClawConfig
from .generator import ArticleGenerator, ArticleLength, WritingMode


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
        qp.setBrush(QColor(28, 32, 40, 230))
        qp.drawEllipse(rect)

        # 背景圆环（白色低透明度轨道）
        pen = QPen(QColor(255, 255, 255, 30), 5, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        qp.setPen(pen)
        qp.drawArc(rect.toRect(), 0, 360 * 16)

        # 渐变色尾迹弧：从透明→主题蓝，弧长270°
        arc_len = 270
        steps = 18
        for i in range(steps):
            alpha = int(255 * (i + 1) / steps)
            color = QColor(99, 179, 255, alpha)
            pen = QPen(color, 5, Qt.PenStyle.SolidLine)
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
                background-color: rgba(28, 32, 40, 215);
                border-radius: 16px;
                border: 1px solid rgba(255,255,255,0.10);
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
        config_override: Optional[OpenClawConfig] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._topic = topic
        self._audience = audience
        self._style = style
        self._length = length
        self._mode = mode
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
            )
            self.finished.emit(content)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OpenClaw - 公众号写作助手")
        self.resize(960, 640)

        self._worker: Optional[GenerateWorker] = None
        self._last_topic: str = ""

        self._build_ui()
        self._build_menu()

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        self._central_widget = central

        layout = QHBoxLayout(central)
        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)

        # ---------- 文章 ----------
        article_group = QGroupBox("文章")
        article_layout = QGridLayout(article_group)
        article_layout.setColumnStretch(1, 1)

        self.topic_edit = QLineEdit()
        self.topic_edit.setPlaceholderText("必填")
        self.audience_edit = QLineEdit()
        self.style_edit = QLineEdit()

        self.length_combo = QComboBox()
        self.length_combo.addItem("中等", "medium")
        self.length_combo.addItem("偏短", "short")
        self.length_combo.addItem("偏长", "long")

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("标准干货", "standard")
        self.mode_combo.addItem("故事化", "story")
        self.mode_combo.addItem("案例拆解", "case_study")
        self.mode_combo.addItem("清单文", "listicle")
        self.mode_combo.addItem("深度分析", "analysis")

        self.style_preset_combo = QComboBox()
        self.style_preset_combo.addItem("无", "")
        self.style_preset_combo.addItem("科普聊天", "通俗易懂、像跟朋友聊天一样的科普风格。")
        self.style_preset_combo.addItem("职场干货", "结构清晰、观点明确、偏职场实战干货。")
        self.style_preset_combo.addItem("故事分享", "通过个人故事或案例来讲道理，轻松、有画面感。")
        self.style_preset_combo.addItem("运营拆解", "以拆解案例为主，有步骤、有数据、有总结。")
        self.style_preset_combo.currentIndexChanged.connect(self._on_style_preset_changed)

        self.generate_button = QPushButton("生成文章")
        self.generate_button.clicked.connect(self._on_generate_clicked)

        r = 0
        article_layout.addWidget(QLabel("主题"), r, 0)
        article_layout.addWidget(self.topic_edit, r, 1)
        r += 1
        article_layout.addWidget(QLabel("读者"), r, 0)
        article_layout.addWidget(self.audience_edit, r, 1)
        r += 1
        article_layout.addWidget(QLabel("风格"), r, 0)
        article_layout.addWidget(self.style_edit, r, 1)
        r += 1
        article_layout.addWidget(QLabel("预设"), r, 0)
        article_layout.addWidget(self.style_preset_combo, r, 1)
        r += 1
        article_layout.addWidget(QLabel("长度"), r, 0)
        article_layout.addWidget(self.length_combo, r, 1)
        r += 1
        article_layout.addWidget(QLabel("模式"), r, 0)
        article_layout.addWidget(self.mode_combo, r, 1)
        r += 1
        article_layout.addWidget(self.generate_button, r, 0, 1, 2)

        # ---------- 账号配置 ----------
        config_group = QGroupBox("账号配置")
        config_layout = QVBoxLayout(config_group)

        self.ark_api_key_edit = QLineEdit()
        self.ark_api_key_edit.setEchoMode(QLineEdit.Password)
        self.ark_api_key_edit.setPlaceholderText("豆包 Key")
        self.ark_model_edit = QLineEdit()
        self.ark_model_edit.setPlaceholderText("豆包模型 ID")

        self.wechat_appid_edit = QLineEdit()
        self.wechat_appid_edit.setPlaceholderText("")
        self.wechat_appsecret_edit = QLineEdit()
        self.wechat_appsecret_edit.setEchoMode(QLineEdit.Password)
        self.wechat_appsecret_edit.setPlaceholderText("")
        self.wechat_thumb_media_id_edit = QLineEdit()
        self.wechat_thumb_media_id_edit.setPlaceholderText("封面图 ID")

        self.ark_api_key_edit.setText(os.getenv("ARK_API_KEY", ""))
        self.ark_model_edit.setText(os.getenv("ARK_MODEL", ""))
        self.wechat_appid_edit.setText(os.getenv("WECHAT_APPID", ""))
        self.wechat_appsecret_edit.setText(os.getenv("WECHAT_APPSECRET", ""))
        self.wechat_thumb_media_id_edit.setText(os.getenv("WECHAT_THUMB_MEDIA_ID", ""))

        # 纵向：标签在上，输入框在下
        config_layout.addWidget(QLabel("豆包 Key"))
        config_layout.addWidget(self.ark_api_key_edit)
        config_layout.addWidget(QLabel("豆包模型"))
        config_layout.addWidget(self.ark_model_edit)
        config_layout.addWidget(QLabel("公众号 AppID"))
        config_layout.addWidget(self.wechat_appid_edit)
        config_layout.addWidget(QLabel("公众号 Secret"))
        config_layout.addWidget(self.wechat_appsecret_edit)
        config_layout.addWidget(QLabel("封面图 thumb_media_id"))
        self.upload_thumb_button = QPushButton("📁 上传图片")
        self.upload_thumb_button.setToolTip(
            "PNG → type=thumb（≤64KB）\nJPG → type=image（≤10MB）\n上传后自动填入 thumb_media_id"
        )
        self.upload_thumb_button.clicked.connect(self._on_upload_thumb_clicked)
        config_layout.addWidget(self.upload_thumb_button)
        config_layout.addWidget(self.wechat_thumb_media_id_edit)
        thumb_hint = QLabel("PNG或 JPG(大小遵循公众号规定)，自动识别格式")
        thumb_hint.setStyleSheet("color: gray; font-size: 11px;")
        config_layout.addWidget(thumb_hint)

        left_col.addWidget(config_group)
        left_col.addWidget(article_group)

        # ---------- 右侧结果 ----------
        result_group = QGroupBox("生成结果")
        result_layout = QVBoxLayout(result_group)

        self.result_edit = QPlainTextEdit()
        self.result_edit.setPlaceholderText("生成后的 Markdown 显示在此。")
        self.result_edit.setLineWrapMode(QPlainTextEdit.NoWrap)

        buttons_bar = QHBoxLayout()
        self.copy_button = QPushButton("复制")
        self.copy_button.clicked.connect(self._copy_result_to_clipboard)
        self.clear_button = QPushButton("清空")
        self.clear_button.clicked.connect(self._clear_result)
        self.send_wechat_button = QPushButton("发到公众号草稿")
        self.send_wechat_button.clicked.connect(self._send_to_wechat_draft)
        buttons_bar.addWidget(self.copy_button)
        buttons_bar.addWidget(self.clear_button)
        buttons_bar.addWidget(self.send_wechat_button)
        buttons_bar.addStretch(1)

        result_layout.addWidget(self.result_edit)
        result_layout.addLayout(buttons_bar)

        layout.addLayout(left_col, 0)
        layout.addWidget(result_group, 1)

        # 加载遮罩（生成文章时显示）
        self._loading_overlay = LoadingOverlay(central, "正在生成文章...")
        central.installEventFilter(self)

    def eventFilter(self, obj: QWidget, event: QEvent) -> bool:
        if obj is self._central_widget and event.type() == QEvent.Type.Resize:
            self._loading_overlay.setGeometry(self._central_widget.rect())
        return super().eventFilter(obj, event)

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

    def _on_style_preset_changed(self) -> None:
        preset = self.style_preset_combo.currentData()
        # 只有当用户还没自己写风格时，才自动填充预设，避免覆盖用户输入
        if preset and not self.style_edit.text().strip():
            self.style_edit.setText(preset)

    def _on_generate_clicked(self) -> None:
        topic = self.topic_edit.text().strip()
        if not topic:
            QMessageBox.warning(self, "提示", "请先填写文章主题。")
            return

        audience = self.audience_edit.text().strip() or None
        style = self.style_edit.text().strip() or None
        length_value = self.length_combo.currentData()
        length: ArticleLength = length_value  # type: ignore[assignment]
        mode_value = self.mode_combo.currentData()
        mode: WritingMode = mode_value  # type: ignore[assignment]

        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "提示", "正在生成中，请稍候……")
            return

        self.generate_button.setEnabled(False)
        self.generate_button.setText("生成中...")
        self._loading_overlay.show_overlay("正在生成文章...")

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
            )

        self._worker = GenerateWorker(
            topic=topic,
            audience=audience,
            style=style,
            length=length,
            mode=mode,
            config_override=config_override,
            parent=self,
        )
        self._worker.finished.connect(self._on_generate_finished)
        self._worker.failed.connect(self._on_generate_failed)
        self._worker.start()

    def _on_generate_finished(self, content: str) -> None:
        self._loading_overlay.hide_overlay()
        self.generate_button.setEnabled(True)
        self.generate_button.setText("生成文章")
        self.result_edit.setPlainText(content)

    def _on_generate_failed(self, message: str) -> None:
        self._loading_overlay.hide_overlay()
        self.generate_button.setEnabled(True)
        self.generate_button.setText("生成文章")
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
        """直接调微信 API 上传封面图，根据格式自动选 type，自动填入 thumb_media_id。"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择封面图（PNG ≤64KB / JPG ≤10MB）",
            str(Path.home()),
            "封面图 (*.jpg *.jpeg *.png)",
        )
        if not filename:
            return

        # 根据扩展名判断上传类型和限制
        suffix = Path(filename).suffix.lower()
        if suffix == ".png":
            media_type = "thumb"          # PNG → type=thumb，微信限制 ≤64KB
            size_limit = 64 * 1024
            size_desc = "64KB"
            mime_type = "image/png"
        elif suffix in (".jpg", ".jpeg"):
            media_type = "image"          # JPG → type=image，微信限制 ≤10MB
            size_limit = 10 * 1024 * 1024
            size_desc = "10MB"
            mime_type = "image/jpeg"
        else:
            QMessageBox.warning(
                self, "格式不支持",
                f"仅支持 PNG（≤64KB）和 JPG（≤10MB）。\n当前文件：{Path(filename).name}",
            )
            return

        appid = self.wechat_appid_edit.text().strip()
        appsecret = self.wechat_appsecret_edit.text().strip()
        if not appid or not appsecret:
            appid = os.getenv("WECHAT_APPID", "").strip()
            appsecret = os.getenv("WECHAT_APPSECRET", "").strip()
        if not appid or not appsecret:
            QMessageBox.warning(self, "缺少配置", "请先填写公众号 AppID 和 Secret。")
            return

        self.upload_thumb_button.setEnabled(False)
        self.upload_thumb_button.setText("上传中...")
        self._loading_overlay.show_overlay("正在上传封面图")
        error_msg: Optional[str] = None
        thumb_id = ""
        try:
            with open(filename, "rb") as f:
                file_bytes = f.read()

            # 大小校验
            if len(file_bytes) > size_limit:
                error_msg = (
                    f"{suffix.upper()} 封面图不能超过 {size_desc}，"
                    f"当前大小：{len(file_bytes) / 1024:.1f} KB。\n"
                    "请压缩图片后重试。"
                )
                return

            # 1. 获取 access_token
            token_resp = requests.get(
                "https://api.weixin.qq.com/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": appid,
                    "secret": appsecret,
                },
                timeout=15,
            )
            token_data = token_resp.json()
            access_token = token_data.get("access_token", "")
            if not access_token:
                error_msg = (
                    f"无法获取 access_token：\n{token_data}\n\n"
                    "请检查 AppID/Secret 是否正确，以及服务器 IP 是否在白名单中。"
                )
                return

            # 2. 上传封面图（PNG→thumb / JPG→image）
            fname = Path(filename).name
            upload_resp = requests.post(
                "https://api.weixin.qq.com/cgi-bin/material/add_material",
                params={"access_token": access_token, "type": media_type},
                files={"media": (fname, file_bytes, mime_type)},
                timeout=30,
            )
            data = upload_resp.json()
            thumb_id = data.get("media_id", "")
            if not thumb_id:
                error_msg = f"未获取到 media_id：\n{data}"
                return

            self.wechat_thumb_media_id_edit.setText(thumb_id)

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

        backend_base = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
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

