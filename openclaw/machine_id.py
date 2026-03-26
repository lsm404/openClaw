"""本机机器码：用于激活码与设备绑定（Windows 优先，其它平台有降级方案）。"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import subprocess
import sys


def _run_text(args: list[str], timeout: float = 15.0) -> str:
    kwargs: dict = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(args, **kwargs)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 or not out:
        return ""
    return out


def _collect_fingerprint_parts() -> list[str]:
    parts: list[str] = []
    if sys.platform == "win32":
        uuid = _run_text(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystemProduct).UUID",
            ]
        )
        if uuid and uuid.upper() != "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF":
            parts.append(f"uuid:{uuid}")
        board = _run_text(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_BaseBoard).SerialNumber",
            ]
        )
        if board and board.lower() not in ("none", "default string", "to be filled by o.e.m."):
            parts.append(f"board:{board}")
        vol = _run_text(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_DiskDrive | Select-Object -First 1).SerialNumber",
            ]
        )
        if vol:
            parts.append(f"disk:{vol}")
    parts.append(f"node:{platform.node()}")
    parts.append(f"machine:{platform.machine()}")
    parts.append(f"user:{os.environ.get('USERNAME') or os.environ.get('USER') or ''}")
    return parts


def get_machine_id() -> str:
    """
    返回稳定、可展示的机器码（32 位十六进制，分 8 组，便于复制与客服核对）。
    同一台物理机多次调用应一致；重装系统后可能变化（取决于硬件信息是否仍可读）。
    """
    raw = "|".join(_collect_fingerprint_parts())
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:32]
    return "-".join(digest[i : i + 4] for i in range(0, 32, 4))


def normalize_activation_code(code: str) -> str:
    """去掉空格与连字符，统一大写，便于与后端一致。"""
    return re.sub(r"[\s\-]+", "", (code or "").strip()).upper()
