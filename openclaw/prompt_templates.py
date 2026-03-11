from textwrap import dedent
from typing import Optional


def build_article_system_prompt() -> str:
    return dedent(
        """
        你是一名资深新媒体运营，擅长写微信公众号文章。

        要求：
        - 用地道、自然的中文写作，避免生硬直译。
        - 文章结构清晰，有「标题 / 引言 / 小标题分节 / 结尾」。
        - 每个小节都有具体案例、比喻或操作建议，避免空洞大话。
        - 默认输出为 Markdown 格式，方便复制到公众号编辑器。
        """
    ).strip()


def build_article_user_prompt(
    topic: str,
    audience: Optional[str],
    style: Optional[str],
    length: str,
    mode: str = "standard",
) -> str:
    length_mapping = {
        "short": "偏短，约 800~1200 字，适合快读。",
        "medium": "中等长度，约 1500~2200 字，适合一般公众号文章。",
        "long": "偏长，约 2500~3500 字，适合深度长文。",
    }
    length_desc = length_mapping.get(length, length_mapping["medium"])

    mode_desc_mapping = {
        "standard": "标准公众号干货文，结构清晰、信息密度适中，适合大部分读者。",
        "story": "故事化表达，通过人物、情节和对话来传递观点，更有代入感。",
        "case_study": "案例拆解风格，从一个或多个实际具体案例入手，做拆解和总结，注意一定是实际案例，而不是想象或虚构的案例。",
        "listicle": "清单/条目型内容，用 5-10 条要点列出关键观点，适合快速浏览。",
        "analysis": "深度分析风格，有背景、问题、分析、结论，适合中长文。",
    }
    mode_desc = mode_desc_mapping.get(mode, mode_desc_mapping["standard"])

    parts: list[str] = [
        "请根据下面信息，生成一篇公众号文章初稿：",
        f"- 主题：{topic}",
        f"- 预期长度：{length_desc}",
        f"- 写作模式：{mode_desc}",
    ]

    if audience:
        parts.append(f"- 目标读者：{audience}")

    if style:
        parts.append(f"- 写作风格偏好：{style}")

    parts.append(
        dedent(
            """
            输出格式要求（非常重要）：
            1. 只输出一篇**可以直接发布**的公众号文章，不要输出你的思考过程，不要输出任何「大纲 / 提纲 / 引言版本 / 正文说明」之类的中间产物。
            2. 从一个你认为最合适的主标题开始（不要给多个可选标题），使用一级标题语法，例如：`# 标题内容`。
            3. 标题下面直接进入文章内容，可以有简短引言，但不要单独写「引言」「版本1」等小标题。
            4. 正文内部自行组织结构：
               - 需要分节时，用 `##` 或 `###` 做小标题，但小标题内容就是文章小节标题，不要是「大纲」「正文」这类元信息。
               - 合理使用粗体、列表来增强可读性。
               - 段落长度适中，不要太长。
            5. **禁止**输出多版本标题、多版本开头或大纲列表；如果你在思考，可以在内部完成思考，只把最终选定的版本写出来。
            6. 不要出现任何英文提示词解释，只输出文章本身相关内容。
            """
        ).strip()
    )

    return "\n".join(parts)

