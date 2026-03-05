from __future__ import annotations

from typing import Literal, Optional

from openai import OpenAI

from .config import OpenClawConfig
from .prompt_templates import build_article_system_prompt, build_article_user_prompt


ArticleLength = Literal["short", "medium", "long"]
WritingMode = Literal["standard", "story", "case_study", "listicle", "analysis"]


class ArticleGenerator:
    def __init__(self, config: OpenClawConfig) -> None:
        self._config = config
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )

    def generate(
        self,
        topic: str,
        audience: Optional[str] = None,
        style: Optional[str] = None,
        length: ArticleLength = "medium",
        mode: WritingMode = "standard",
    ) -> str:
        system_prompt = build_article_system_prompt()
        user_prompt = build_article_user_prompt(
            topic=topic,
            audience=audience,
            style=style,
            length=length,
            mode=mode,
        )

        completion = self._client.responses.create(
            model=self._config.model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": system_prompt},
                        {"type": "input_text", "text": user_prompt},
                    ],
                }
            ],
        )

        # 从 output[0].content 中拼接文本，避免某些实现里对 output_text 进行 JSON 转义
        try:
            chunks = []
            for item in completion.output[0].content:
                # 兼容 OpenAI Responses: 文本块类型通常为 "output_text"
                if getattr(item, "type", "") in {"output_text", "message", "text"}:
                    text = getattr(item, "text", None)
                    if text:
                        chunks.append(text)
            if chunks:
                return "".join(chunks)
        except Exception:
            # 回退到 SDK 自带的便捷属性
            return getattr(completion, "output_text", str(completion))

        return getattr(completion, "output_text", "")

