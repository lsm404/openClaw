import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 始终从项目根目录（openClaw/）加载 .env，避免 uvicorn 工作目录不是项目根时读不到 OPENCLAW_LICENSE_CODES
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE, override=True)


@dataclass
class WechatConfig:
    appid: str
    appsecret: str
    base_url: str = "https://api.weixin.qq.com"
    thumb_media_id: str | None = None


def load_wechat_config() -> WechatConfig:
    appid = os.getenv("WECHAT_APPID", "").strip()
    appsecret = os.getenv("WECHAT_APPSECRET", "").strip()
    if not appid or not appsecret:
        raise RuntimeError("未配置 WECHAT_APPID / WECHAT_APPSECRET。")

    base_url = os.getenv("WECHAT_BASE_URL", "https://api.weixin.qq.com").strip()
    thumb_media_id = os.getenv("WECHAT_THUMB_MEDIA_ID", "").strip() or None
    return WechatConfig(
        appid=appid,
        appsecret=appsecret,
        base_url=base_url,
        thumb_media_id=thumb_media_id,
    )

