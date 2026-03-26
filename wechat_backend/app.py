from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any, Dict, Optional

import markdown
import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from starlette.requests import Request

from .config import WechatConfig, load_wechat_config
from .license_db import bind_or_verify, load_allowed_codes, normalize_code

_LOG = logging.getLogger("openclaw")


def _configure_openclaw_logging() -> None:
    """独立 handler + 立即刷 stderr，避免 print 在部分终端下不显示。"""
    _LOG.setLevel(logging.INFO)
    if _LOG.handlers:
        return
    h = logging.StreamHandler(sys.stderr)
    h.setLevel(logging.INFO)
    h.setFormatter(logging.Formatter("%(levelname)s [openclaw] %(message)s"))
    _LOG.addHandler(h)
    _LOG.propagate = False


app = FastAPI(title="OpenClaw WeChat Backend", version="0.1.0")
_configure_openclaw_logging()


@app.middleware("http")
async def _openclaw_request_log_middleware(request: Request, call_next: Any) -> Any:
    _LOG.info("%s %s", request.method, request.url.path)
    return await call_next(request)


@app.on_event("startup")
def _log_license_pool_on_startup() -> None:
    import os
    from pathlib import Path

    from .license_db import (
        DOTENV_CWD,
        DOTENV_LOCAL_CODES,
        DOTENV_PROJECT_ROOT,
        load_allowed_codes,
    )

    raw = os.getenv("OPENCLAW_LICENSE_CODES", "")
    n = len(load_allowed_codes())
    _LOG.info(
        "OPENCLAW_LICENSE_CODES 读取自 os.environ（load_dotenv：先 cwd/.env 再 项目根/.env，后者优先覆盖；"
        "若仍空则由 license_db 从项目根 .env / local_activation_codes.env / OPENCLAW_DOTENV_PATH 兜底解析）"
    )
    _LOG.info(
        "  项目根 .env: %s 存在=%s",
        DOTENV_PROJECT_ROOT,
        DOTENV_PROJECT_ROOT.is_file(),
    )
    _LOG.info(
        "  local_activation_codes.env: %s 存在=%s",
        DOTENV_LOCAL_CODES,
        DOTENV_LOCAL_CODES.is_file(),
    )
    _LOG.info(
        "  当前工作目录 .env: %s 存在=%s (cwd=%s)",
        DOTENV_CWD,
        DOTENV_CWD.is_file(),
        Path.cwd(),
    )
    _LOG.info(
        "  变量已设置长度(字符): %s → 解析后激活码条数: %s",
        len(raw.strip()),
        n,
    )
    if n == 0:
        _LOG.warning(
            "未配置 OPENCLAW_LICENSE_CODES。请在环境变量或项目根 .env 中设置逗号分隔的激活码。"
        )


class LicenseActivateRequest(BaseModel):
    activation_code: str
    machine_id: str


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


@app.get("/license/pool-size")
def license_pool_size() -> dict[str, int]:
    """本地自检：当前进程合并后的激活码池条目数（不含已绑定逻辑）。"""
    from .license_db import load_allowed_codes

    return {"n": len(load_allowed_codes())}


@app.post("/license/activate")
def license_activate(req: LicenseActivateRequest) -> dict[str, Any]:
    """
    激活码首次使用会绑定 machine_id；同一机器重复调用返回成功；
    已绑定其它机器则拒绝。
    """
    pool_n = len(load_allowed_codes())
    code_n = normalize_code(req.activation_code)
    mid = (req.machine_id or "").strip()
    _LOG.info(
        "POST /license/activate pool_size=%s code_norm=%s… len=%s machine_id=%s…",
        pool_n,
        code_n[:16],
        len(code_n),
        mid[:24],
    )
    ok, message = bind_or_verify(req.activation_code, req.machine_id)
    _LOG.info("activate result ok=%s detail=%s", ok, message[:160])
    if ok:
        return {"ok": True, "message": message}
    if "其它设备" in message:
        raise HTTPException(status_code=403, detail=message)
    raise HTTPException(status_code=400, detail=message)


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

