"""
小说生成提示词模板
"""
from textwrap import dedent


def build_novel_system_prompt(genre: str = "short") -> str:
    """小说写作系统提示词"""
    length_hint = "短篇" if genre == "short" else "长篇"
    return dedent(f"""
    你是一位资深小说作家，擅长写{length_hint}小说。
    
    要求：
    - 根据前情摘要和上一章结尾，续写下一章
    - 保持人物性格、世界观、叙事风格一致
    - 每章结尾留有悬念或自然过渡，便于续写
    - 用地道、自然的中文写作
    - 输出为 Markdown 格式
    """).strip()


def build_novel_user_prompt(
    title: str,
    synopsis: str,
    previous_summaries: list[str],
    last_chapter_ending: str,
    chapter_hint: str = "",
) -> str:
    """构建续写用户提示（人物由 AI 根据简介自动生成）"""
    parts = []

    parts.append("【小说信息】")
    parts.append(f"标题：{title}")
    parts.append(f"简介：{synopsis}")
    parts.append("（人物根据简介和剧情发展，由你自行设定与刻画）")
    parts.append("")

    if previous_summaries:
        parts.append("【前情摘要】")
        for i, s in enumerate(previous_summaries, 1):
            parts.append(f"第{i}章：{s}")
        parts.append("")

    if last_chapter_ending.strip():
        parts.append("【上一章结尾】")
        parts.append(last_chapter_ending.strip())
        parts.append("")

    parts.append("【本章要求】")
    if chapter_hint.strip():
        parts.append(f"请续写下一章，本章梗概/标题：{chapter_hint}")
    else:
        parts.append("请续写下一章。")
    parts.append("直接输出本章正文，无需重复前情。")

    return "\n".join(parts)


def build_summary_prompt(chapter_content: str) -> str:
    """构建本章摘要的提示"""
    return dedent(f"""
    请用 1-3 句话概括以下章节内容，用于后续章节的前情提要。只输出摘要，不要其他内容。

    ---
    {chapter_content[:3000]}
    ---
    """).strip()
