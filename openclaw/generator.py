from __future__ import annotations

from typing import Literal, Optional

from openai import OpenAI

from .config import OpenClawConfig
from .prompt_templates import (
    build_article_system_prompt,
    build_article_user_prompt,
    build_rewrite_user_prompt,
)


ArticleLength = Literal["short", "medium", "long"]
WritingMode = Literal["standard", "story", "case_study", "listicle", "analysis"]
CreationMode = Literal["original", "rewrite"]
RewriteGoal = Literal[
    "new_article",
    "new_angle",
    "more_conversational",
    "more_actionable",
]
ReferenceFocus = Literal["structure", "tone", "opening", "mixed"]
ReferenceLevel = Literal["low", "medium", "high"]
ExpressionMode = Literal["standard", "conversational", "de_ai", "opinionated"]


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
        system_prompt: Optional[str] = None,
        creation_mode: CreationMode = "original",
        source_article: Optional[str] = None,
        rewrite_goal: RewriteGoal = "new_article",
        reference_focus: ReferenceFocus = "mixed",
        reference_level: ReferenceLevel = "medium",
        expression_mode: ExpressionMode = "standard",
    ) -> str:
        if system_prompt is None:
            system_prompt = build_article_system_prompt()

        markdown_reminder = "默认输出为 Markdown 格式，方便复制到公众号编辑器。"
        if system_prompt and markdown_reminder not in system_prompt:
            system_prompt = system_prompt.rstrip() + "\n- " + markdown_reminder

        if creation_mode == "rewrite":
            user_prompt = build_rewrite_user_prompt(
                source_article=source_article or "",
                topic=topic or None,
                audience=audience,
                style=style,
                length=length,
                mode=mode,
                rewrite_goal=rewrite_goal,
                reference_focus=reference_focus,
                reference_level=reference_level,
                expression_mode=expression_mode,
            )
        else:
            user_prompt = build_article_user_prompt(
                topic=topic,
                audience=audience,
                style=style,
                length=length,
                mode=mode,
                expression_mode=expression_mode,
            )

        extra_kwargs: dict = {}
        if self._config.enable_web_search:
            extra_kwargs["tools"] = [{"type": "web_search"}]

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
            **extra_kwargs,
        )

        try:
            chunks = []
            for item in completion.output[0].content:
                if getattr(item, "type", "") in {"output_text", "message", "text"}:
                    text = getattr(item, "text", None)
                    if text:
                        chunks.append(text)
            if chunks:
                return "".join(chunks)
        except Exception:
            return getattr(completion, "output_text", str(completion))

        return getattr(completion, "output_text", "")
