"""
小说续写与摘要生成
"""
from __future__ import annotations

from typing import Optional

from openai import OpenAI

from .config import OpenClawConfig
from .novel_prompts import (
    build_novel_system_prompt,
    build_novel_user_prompt,
    build_summary_prompt,
)
from .novel_store import Chapter, Novel


def _call_model(
    client: OpenAI,
    config: OpenClawConfig,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """调用模型"""
    extra = {}
    if config.enable_web_search:
        extra["tools"] = [{"type": "web_search"}]

    completion = client.responses.create(
        model=config.model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": system_prompt},
                    {"type": "input_text", "text": user_prompt},
                ],
            }
        ],
        **extra,
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
        pass
    return getattr(completion, "output_text", "")


def generate_next_chapter(
    config: OpenClawConfig,
    novel: Novel,
    chapter_hint: str = "",
) -> str:
    """
    生成下一章正文。
    - 传入前几章摘要 + 上一章结尾
    - 返回本章正文
    """
    client = OpenAI(api_key=config.api_key, base_url=config.base_url)

    # 前情摘要：最近 5 章，避免 token 过多
    summaries = [c.summary for c in novel.chapters[-5:] if c.summary]

    # 上一章结尾：取最后约 800 字
    last_ending = ""
    if novel.chapters:
        last = novel.chapters[-1].content
        last_ending = last[-800:] if len(last) > 800 else last

    user_prompt = build_novel_user_prompt(
        title=novel.title,
        synopsis=novel.synopsis,
        previous_summaries=summaries,
        last_chapter_ending=last_ending,
        chapter_hint=chapter_hint,
    )

    system_prompt = build_novel_system_prompt(genre=novel.genre)

    return _call_model(client, config, system_prompt, user_prompt)


def generate_chapter_summary(config: OpenClawConfig, content: str) -> str:
    """自动生成章节摘要"""
    if not content.strip():
        return ""

    client = OpenAI(api_key=config.api_key, base_url=config.base_url)
    system = "你是一个摘要助手，用 1-3 句话概括章节内容，只输出摘要。"
    user = build_summary_prompt(content)
    return _call_model(client, config, system, user).strip()
