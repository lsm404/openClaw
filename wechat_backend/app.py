from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import markdown
import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from .config import WechatConfig, load_wechat_config


app = FastAPI(title="OpenClaw WeChat Backend", version="0.1.0")


class DraftRequest(BaseModel):
    title: str
    content_md: str
    digest: Optional[str] = None
    author: Optional[str] = None
    # 可选：前端传入的公众号配置（不传则使用后端环境变量）
    wechat_appid: Optional[str] = None
    wechat_appsecret: Optional[str] = None
    wechat_thumb_media_id: Optional[str] = None
    wechat_base_url: Optional[str] = None


class TokenCache:
    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._expire_at: float = 0.0
        self._appid: Optional[str] = None
        self._appsecret: Optional[str] = None

    def get(self, config: WechatConfig) -> str:
        now = time.time()
        same_cred = self._appid == config.appid and self._appsecret == config.appsecret
        if self._token and same_cred and now < self._expire_at - 60:
            return self._token

        resp = requests.get(
            f"{config.base_url}/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": config.appid,
                "secret": config.appsecret,
            },
            timeout=10,
        )
        data: Dict[str, Any] = resp.json()
        if "access_token" not in data:
            errcode = data.get("errcode", 0)
            if errcode == 40164:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "获取 access_token 失败: 当前服务器 IP 未在公众号白名单中 (errcode 40164)。"
                        "请登录微信公众平台 → 开发 → 基本配置 → IP 白名单，添加本机公网 IP 后重试。"
                    ),
                )
            raise HTTPException(
                status_code=500,
                detail=f"获取 access_token 失败: {data}",
            )
        self._token = data["access_token"]
        self._expire_at = now + float(data.get("expires_in", 3600))
        self._appid = config.appid
        self._appsecret = config.appsecret
        return self._token


token_cache = TokenCache()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/wechat/upload_thumb")
def upload_thumb(
    file: UploadFile = File(...),
    wechat_appid: Optional[str] = Form(None),
    wechat_appsecret: Optional[str] = Form(None),
) -> dict[str, Any]:
    """
    上传图片到公众号永久素材，返回 thumb_media_id。
    微信要求：jpg/png，大小 ≤ 1MB，尺寸 200×200 ~ 900×500。
    """
    if wechat_appid and wechat_appsecret:
        config = WechatConfig(
            appid=wechat_appid.strip(),
            appsecret=wechat_appsecret.strip(),
            base_url="https://api.weixin.qq.com",
            thumb_media_id=None,
        )
    else:
        config = load_wechat_config()

    access_token = token_cache.get(config)

    filename = file.filename or "cover.jpg"
    content_type = file.content_type or "image/jpeg"
    file_bytes = file.file.read()

    resp = requests.post(
        f"{config.base_url}/cgi-bin/material/add_material",
        params={"access_token": access_token, "type": "image"},
        files={"media": (filename, file_bytes, content_type)},
        timeout=30,
    )
    data: Dict[str, Any] = resp.json()
    if "media_id" not in data:
        raise HTTPException(
            status_code=500,
            detail=f"上传封面图失败: {data}",
        )
    return {"thumb_media_id": data["media_id"], "url": data.get("url", "")}


@app.post("/wechat/draft")
def create_wechat_draft(req: DraftRequest) -> dict[str, Any]:
    """
    将 Markdown 文章发送到公众号草稿箱。
    """
    # 1. 优先使用前端传入的公众号配置；未传则回退到后端环境变量
    if req.wechat_appid and req.wechat_appsecret:
        base_url = (req.wechat_base_url or "https://api.weixin.qq.com").strip()
        config = WechatConfig(
            appid=req.wechat_appid.strip(),
            appsecret=req.wechat_appsecret.strip(),
            base_url=base_url,
            thumb_media_id=(req.wechat_thumb_media_id or None),
        )
    else:
        config = load_wechat_config()
        # 允许只通过前端覆盖封面图 ID
        if req.wechat_thumb_media_id:
            config.thumb_media_id = req.wechat_thumb_media_id.strip()

    access_token = token_cache.get(config)

    # 调试：打印前一小段 markdown 内容，方便确认是否为 \\uXXXX 形式
    sample = req.content_md[:200]
    print("=== [wechat_backend] content_md sample ===")
    print(sample)
    print("=========================================")

    content_md = req.content_md

    # Markdown → HTML 基础转换
    content_html = markdown.markdown(content_md, extensions=["extra"])

    # 包一层适配公众号阅读体验的样式
    styled_html = f"""
<div class="openclaw-article" style="font-size:16px;line-height:1.75;color:#333333;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;padding:12px 0;">
  <style>
    .openclaw-article h1, .openclaw-article h2, .openclaw-article h3 {{
      font-weight: 600;
      color: #111111;
      margin: 1.4em 0 0.6em;
    }}
    .openclaw-article h1 {{
      font-size: 22px;
    }}
    .openclaw-article h2 {{
      font-size: 20px;
      border-left: 4px solid #1890ff;
      padding-left: 8px;
    }}
    .openclaw-article h3 {{
      font-size: 18px;
    }}
    .openclaw-article p {{
      margin: 0.8em 0;
    }}
    .openclaw-article ul,
    .openclaw-article ol {{
      padding-left: 1.4em;
      margin: 0.6em 0;
    }}
    .openclaw-article strong {{
      color: #111111;
    }}
    .openclaw-article blockquote {{
      border-left: 3px solid #e6e6e6;
      padding-left: 10px;
      color: #666666;
      margin: 1em 0;
    }}
    .openclaw-article code {{
      background: #f5f5f5;
      padding: 2px 4px;
      border-radius: 3px;
      font-size: 0.9em;
    }}
  </style>
  {content_html}
</div>
""".strip()

    if not config.thumb_media_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "未配置封面图 thumb_media_id。"
                "可以在 .env 中设置 WECHAT_THUMB_MEDIA_ID，"
                "或在前端界面中填写封面图的 thumb_media_id。"
            ),
        )

    payload: Dict[str, Any] = {
        "articles": [
            {
                "title": req.title,
                "author": req.author or "",
                "digest": req.digest or "",
                "content": styled_html,
                "thumb_media_id": config.thumb_media_id,
                "need_open_comment": 0,
                "only_fans_can_comment": 0,
            }
        ]
    }

    # 调试：打印发给微信草稿接口的核心参数
    article = payload["articles"][0]
    print("=== [wechat_backend] payload to wechat ===")
    print("title:", article.get("title"))
    print("digest:", (article.get("digest") or "")[:80])
    content_sample = (article.get("content") or "")[:400]
    print("content_sample:", content_sample)
    print("=========================================")

    resp = requests.post(
        f"{config.base_url}/cgi-bin/draft/add",
        params={"access_token": access_token},
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=15,
    )
    data: Dict[str, Any] = resp.json()
    if data.get("errcode", 0) != 0:
        raise HTTPException(
            status_code=500,
            detail=f"创建草稿失败: {data}",
        )

    return data


def get_app() -> FastAPI:
    return app

