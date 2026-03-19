"""
OpenClaw 小说写作助手 - 命令行入口
"""
from __future__ import annotations

import typer

from .desktop_app import main as run_desktop

app = typer.Typer(add_completion=False, help="OpenClaw 小说写作助手")


@app.command("run")
def run_app() -> None:
    """启动桌面应用"""
    run_desktop()


@app.callback(invoke_without_command=True)
def default(ctx: typer.Context) -> None:
    """默认启动桌面应用"""
    if ctx.invoked_subcommand is None:
        run_desktop()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
