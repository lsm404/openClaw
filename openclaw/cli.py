from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from .config import load_config
from .generator import ArticleGenerator, ArticleLength, WritingMode


app = typer.Typer(add_completion=False, help="OpenClaw 自动写公众号文章草稿的命令行工具。")
console = Console()


def _validate_length(_: str, value: str) -> ArticleLength:
    value_lower = value.lower()
    if value_lower not in {"short", "medium", "long"}:
        raise typer.BadParameter("长度只能是 short / medium / long")
    return value_lower  # type: ignore[return-value]


def _validate_mode(_: str, value: str) -> WritingMode:
    value_lower = value.lower()
    allowed = {"standard", "story", "case_study", "listicle", "analysis"}
    if value_lower not in allowed:
        raise typer.BadParameter(
            "写作模式只能是 standard / story / case_study / listicle / analysis"
        )
    return value_lower  # type: ignore[return-value]


@app.command("article")
def generate_article(
    topic: str = typer.Option(..., "--topic", "-t", help="文章主题（必填）"),
    audience: Optional[str] = typer.Option(
        None, "--audience", "-a", help="目标读者画像，例如：程序员、职场新人"
    ),
    style: Optional[str] = typer.Option(
        None, "--style", "-s", help="写作风格，例如：科普+聊天、故事化、职场干货"
    ),
    mode: str = typer.Option(
        "standard",
        "--mode",
        "-m",
        help="写作模式：standard / story / case_study / listicle / analysis",
        callback=_validate_mode,
    ),
    length: str = typer.Option(
        "medium",
        "--length",
        "-l",
        help="文章长度：short / medium / long",
        callback=_validate_length,
    ),
    output: Path = typer.Option(
        Path("openclaw_article.md"),
        "--output",
        "-o",
        help="输出 markdown 文件路径",
    ),
):
    """
    生成一篇公众号文章草稿（标题 + 大纲 + 正文）。
    """
    try:
        config = load_config()
    except RuntimeError as e:
        console.print(Panel(str(e), title="配置错误", style="bold red"))
        raise typer.Exit(code=1) from e

    generator = ArticleGenerator(config)

    console.print(
        Panel.fit(
            f"[bold]正在为你生成文章草稿...[/bold]\n\n"
            f"[bold]主题：[/bold]{topic}\n"
            f"[bold]目标读者：[/bold]{audience or '未指定'}\n"
            f"[bold]风格：[/bold]{style or '未指定'}\n"
            f"[bold]长度：[/bold]{length}\n"
            f"[bold]模式：[/bold]{mode}",
            title="OpenClaw",
            border_style="cyan",
        )
    )

    with console.status("调用大模型生成中，请稍候...", spinner="dots"):
        content = generator.generate(
            topic=topic,
            audience=audience,
            style=style,
            length=length,  # type: ignore[arg-type]
            mode=mode,  # type: ignore[arg-type]
        )

    output.write_text(content, encoding="utf-8")
    console.print(
        Panel.fit(
            f"生成完成！已保存到 [bold green]{output}[/bold green]\n\n"
            f"你可以直接把内容复制到公众号后台，再进行人工润色。",
            title="完成",
            border_style="green",
        )
    )


def main():
    app()


if __name__ == "__main__":
    main()

