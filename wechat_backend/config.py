import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


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

