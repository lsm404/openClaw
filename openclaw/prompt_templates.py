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


def build_article_system_prompt_presets() -> list[str]:
    return [
        build_article_system_prompt(),
        dedent(
            """
            你是一名资深新媒体运营，擅长把复杂内容写成公众号干货文章。

            要求：
            - 语言务实、清晰、利落，少空话、少套话。
            - 优先用步骤拆解、清单列点、方法总结来组织内容。
            - 每一节都尽量给出可执行建议、常见误区或操作示例。
            - 标题和小标题要直接，让读者一眼知道能获得什么。
            - 输出适合直接发布到微信公众号，默认使用 Markdown 格式。
            """
        ).strip(),
        dedent(
            """
            你是一名擅长故事化表达的公众号作者，能把观点写得有代入感、有画面感。

            要求：
            - 文章以真实感的场景、人物经历、问题冲突推进内容。
            - 语言自然、有温度，像和读者聊天，但不要过度煽情。
            - 每个观点都要落回具体案例、细节观察或生活化比喻。
            - 节奏上先吸引读者，再展开分析，最后给出明确结论。
            - 输出适合直接发布到微信公众号，默认使用 Markdown 格式。
            """
        ).strip(),
        dedent(
            """
            你是一名擅长行业观察和深度分析的公众号作者。

            要求：
            - 文章重视背景交代、问题定义、原因分析和结论提炼。
            - 论证要层层推进，避免空泛判断，尽量写出因果关系。
            - 小标题要有观点性，不要只是重复主题。
            - 在分析中加入案例、现象、对比或趋势判断，增强说服力。
            - 输出适合直接发布到微信公众号，默认使用 Markdown 格式。
            """
        ).strip(),
    ]


def _build_output_requirements() -> str:
    return dedent(
        """
        输出格式要求（非常重要）：
        1. 只输出一篇可以直接发布的公众号文章，不要输出你的思考过程，不要输出任何「大纲 / 提纲 / 引言版本 / 正文说明」之类的中间产物。
        2. 从一个你认为最合适的主标题开始，不要给多个可选标题，使用一级标题语法，例如：`# 标题内容`。
        3. 标题下面直接进入文章内容，可以有简短引言，但不要单独写「引言」「版本1」等元信息标题。
        4. 正文内部自行组织结构：
           - 需要分节时，用 `##` 或 `###` 做小标题，但小标题内容就是文章小节标题，不要是「大纲」「正文」这类元信息。
           - 合理使用粗体、列表来增强可读性。
           - 段落长度适中，不要太长。
        5. 禁止输出多版本标题、多版本开头或大纲列表；如果你在思考，可以在内部完成思考，只把最终选定的版本写出来。
        6. 不要出现任何英文提示词解释，只输出文章本身相关内容。
        """
    ).strip()


def _build_expression_requirements(expression_mode: str) -> str:
    mapping = {
        "standard": dedent(
            """
            表达处理要求：
            - 保持正常、自然、清晰的公众号表达，不额外做风格强化。
            """
        ).strip(),
        "conversational": dedent(
            """
            表达处理要求：
            - 整体更口语一点，像在和读者聊天，而不是在写汇报材料。
            - 允许出现短句、插入句和自然停顿，不要每段都过于工整。
            - 少用书面腔和总结腔，多用日常公众号里常见的自然表达。
            """
        ).strip(),
        "de_ai": dedent(
            """
            表达处理要求：
            - 明显降低 AI 腔，不要写成标准答案式总结稿。
            - 不要使用“首先、其次、最后、综上所述、由此可见、值得一提的是、不难发现、赋能、全面提升”等模板化表达。
            - 少写正确但空泛的废话，多写具体场景、具体判断、具体感受。
            - 不要每一段都一样长，不要每个小标题都像汇报提纲。
            - 允许保留一点真人写作时的停顿感、判断感和不那么规整的节奏。
            - 结尾不要强行升华，不要套路式总结。
            """
        ).strip(),
        "opinionated": dedent(
            """
            表达处理要求：
            - 整体更有态度和判断，不要只是中性信息整理。
            - 在关键段落里明确表达“为什么这么看”，增强观点感。
            - 少写放在哪都成立的正确话，多写有倾向性的观察和取舍。
            - 保持克制，不要为了强观点而故意夸张。
            """
        ).strip(),
    }
    return mapping.get(expression_mode, mapping["standard"])


def build_article_user_prompt(
    topic: str,
    audience: Optional[str],
    style: Optional[str],
    length: str,
    mode: str = "standard",
    expression_mode: str = "standard",
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

    parts.append(_build_expression_requirements(expression_mode))
    parts.append(_build_output_requirements())
    return "\n".join(parts)


def build_rewrite_user_prompt(
    source_article: str,
    topic: Optional[str],
    audience: Optional[str],
    style: Optional[str],
    length: str,
    mode: str,
    rewrite_goal: str,
    reference_focus: str,
    reference_level: str,
    expression_mode: str,
) -> str:
    length_mapping = {
        "short": "偏短，约 800~1200 字，适合快读。",
        "medium": "中等长度，约 1500~2200 字，适合一般公众号文章。",
        "long": "偏长，约 2500~3500 字，适合深度长文。",
    }
    length_desc = length_mapping.get(length, length_mapping["medium"])

    mode_desc_mapping = {
        "standard": "标准公众号干货文，结构清晰、信息密度适中。",
        "story": "故事化表达，通过场景和人物推进内容。",
        "case_study": "案例拆解风格，从案例中提炼观点。",
        "listicle": "清单/条目型内容，强调可执行要点。",
        "analysis": "深度分析风格，强调问题、原因、结论。",
    }
    mode_desc = mode_desc_mapping.get(mode, mode_desc_mapping["standard"])

    rewrite_goal_mapping = {
        "new_article": "基于参考文章的主题和切口，写一篇新的原创版本。",
        "new_angle": "保留参考文章的核心话题，但换一个更有新意的切入角度来写。",
        "more_conversational": "保留核心信息，但整体写得更口语、更像和读者聊天。",
        "more_actionable": "保留核心话题，但更强调方法、步骤和可执行建议。",
    }
    rewrite_goal_desc = rewrite_goal_mapping.get(
        rewrite_goal,
        rewrite_goal_mapping["new_article"],
    )

    focus_mapping = {
        "structure": "重点借鉴文章结构和段落推进方式。",
        "tone": "重点借鉴语气、节奏和表达氛围。",
        "opening": "重点借鉴标题切口和开头进入方式。",
        "mixed": "综合借鉴结构、切口和表达节奏。",
    }
    focus_desc = focus_mapping.get(reference_focus, focus_mapping["mixed"])

    level_mapping = {
        "low": "轻度借鉴，只参考大致方向和部分组织方式。",
        "medium": "中度借鉴，参考结构和节奏，但表达和案例必须明显重写。",
        "high": "较高程度借鉴文章组织方式，但仍必须保证最终成稿是新的原创表达，不能出现明显复述。",
    }
    level_desc = level_mapping.get(reference_level, level_mapping["medium"])

    parts: list[str] = [
        "请基于下面的参考文章，写一篇新的公众号文章。",
        "",
        "你的任务不是复述、摘抄或同义替换原文，而是在理解原文结构、切口和表达节奏后，产出一篇新的原创成稿。",
        f"- 改写目标：{rewrite_goal_desc}",
        f"- 借鉴重点：{focus_desc}",
        f"- 参考程度：{level_desc}",
        f"- 预期长度：{length_desc}",
        f"- 写作模式：{mode_desc}",
    ]

    if topic:
        parts.append(f"- 新文章主题：{topic}")
    else:
        parts.append("- 新文章主题：如果未单独指定，请沿用参考文章的核心主题，但必须用新的组织和表达方式完成。")

    if audience:
        parts.append(f"- 目标读者：{audience}")

    if style:
        parts.append(f"- 写作风格偏好：{style}")

    parts.append(
        dedent(
            f"""
            原创要求（必须遵守）：
            1. 可以借鉴参考文章的结构、切口、节奏和信息组织方式，但不能逐句复述，不能大段保留原文表达。
            2. 不要直接照搬原文标题、小标题、金句、案例描述和结尾收束方式。
            3. 如果参考文章里有案例，请改成新的叙述方式，必要时换成更通用的场景化表达。
            4. 如果你发现参考文章有明显的个人化细节、独特表述或强识别句式，必须主动避开，不要复用。
            5. 最终成稿要让读者感觉这是一篇新的文章，而不是原文换词重写。

            参考文章如下：
            {source_article.strip()}
            """
        ).strip()
    )

    parts.append(_build_expression_requirements(expression_mode))
    parts.append(_build_output_requirements())
    return "\n".join(parts)
