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
        - 记住：这是「高质量初稿」，要帮助作者节省 70% 的时间，而不是终稿。
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
            输出格式要求：
            1. 先给出一个你认为最合适的主标题（不要给多个可选标题），使用一级标题语法开头，例如：`# 标题内容`。
            2. 然后给出完整大纲（使用 Markdown 列表，层级清晰）。
            3. 接着给出 2~3 个不同版本的开头段落（引言），供我选择。
            4. 最后给出正文内容：
               - 每个小节都要有小标题（使用 `##` 或 `###`）。
               - 合理使用粗体、列表来增强可读性。
               - 段落长度适中，不要太长。
            5. 不要出现任何英文提示词解释，只输出文章相关内容。
            """
        ).strip()
    )

    return "\n".join(parts)

