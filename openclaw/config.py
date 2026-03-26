import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
# override=True：优先采用项目 .env，避免 Windows 已存在的用户/系统环境变量把 OPENCLAW_* 指向旧远程
load_dotenv(_ENV_FILE, override=True)


@dataclass
class OpenClawConfig:
    api_key: str
    base_url: str
    model: str
    max_retries: int = 3
    # 是否为模型开启联网（web_search 工具）
    enable_web_search: bool = False


def load_config() -> OpenClawConfig:
    # 兼容火山引擎 ARK 的 OpenAI SDK 调用方式
    # https://ark.cn-beijing.volces.com/api/v3
    api_key = os.getenv("ARK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("未找到 ARK_API_KEY，请在项目根目录创建 .env 并配置。")

    base_url = os.getenv(
        "ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
    ).strip()
    model = os.getenv("ARK_MODEL", "").strip()
    if not model:
        raise RuntimeError("未找到 ARK_MODEL，请在 .env 中配置你要使用的模型 ID。")

    # 是否启用联网搜索（web_search 工具）
    enable_web_search = os.getenv("ARK_ENABLE_WEB_SEARCH", "0").strip()
    enable_web_search_flag = enable_web_search.lower() in {"1", "true", "yes", "on"}

    return OpenClawConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        enable_web_search=enable_web_search_flag,
    )

