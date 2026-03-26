"""License pool and activation binding storage for OpenClaw."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional, Set

from dotenv import dotenv_values, load_dotenv

_LOG = logging.getLogger("openclaw")

_DEFAULT_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PROJECT_ROOT = _DEFAULT_ROOT / ".env"
DOTENV_LOCAL_CODES = _DEFAULT_ROOT / "local_activation_codes.env"
DOTENV_CWD = Path.cwd() / ".env"

load_dotenv(DOTENV_CWD, override=True)
load_dotenv(DOTENV_PROJECT_ROOT, override=True)


def _db_path() -> Path:
    raw = os.getenv("OPENCLAW_LICENSE_DB", "").strip()
    if raw:
        return Path(raw)
    return _DEFAULT_ROOT / "data" / "license.db"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    _ensure_parent(path)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS license_bindings (
            code_norm TEXT PRIMARY KEY,
            machine_id TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS license_pool (
            code_norm TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            source TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _parse_codes_csv(raw: str) -> Set[str]:
    out: Set[str] = set()
    for part in raw.split(","):
        code = re.sub(r"[\s\-]+", "", part.strip()).upper()
        if code:
            out.add(code)
    return out


def _strip_inline_env_comment(value: str) -> str:
    for index, char in enumerate(value):
        if char == "#" and (index == 0 or value[index - 1] in " \t"):
            return value[:index].rstrip()
    return value


def _read_openclaw_license_codes_from_file(path: Path) -> str:
    if not path.is_file():
        return ""

    try:
        values = dotenv_values(path)
        raw = (values.get("OPENCLAW_LICENSE_CODES") or "").strip().strip('"').strip("'")
        raw = _strip_inline_env_comment(raw)
        if raw:
            return raw
    except OSError:
        pass

    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return ""

    for line in text.splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        match = re.match(r"^OPENCLAW_LICENSE_CODES\s*=\s*(.*)$", item, flags=re.IGNORECASE)
        if not match:
            continue
        raw = match.group(1).strip().strip('"').strip("'")
        raw = _strip_inline_env_comment(raw)
        if raw:
            return raw

    return ""


_warned_empty_license_env = False


def _ensure_license_codes_from_project_dotenv() -> None:
    global _warned_empty_license_env

    if os.getenv("OPENCLAW_LICENSE_CODES", "").strip():
        return

    candidates: list[Path] = []
    extra = os.getenv("OPENCLAW_DOTENV_PATH", "").strip()
    if extra:
        candidates.append(Path(extra))
    candidates.extend([DOTENV_PROJECT_ROOT, DOTENV_LOCAL_CODES])

    for path in candidates:
        raw = _read_openclaw_license_codes_from_file(path)
        if raw:
            os.environ["OPENCLAW_LICENSE_CODES"] = raw
            return

    if not _warned_empty_license_env:
        _warned_empty_license_env = True
        parts = [f"{path} (exists={path.is_file()})" for path in candidates]
        _LOG.warning(
            "OPENCLAW_LICENSE_CODES is empty; checked %s",
            " -> ".join(parts),
        )


def _load_codes_from_db() -> Set[str]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT code_norm FROM license_pool WHERE status = ?",
            ("active",),
        ).fetchall()
        return {str(row[0]).strip().upper() for row in rows if row and row[0]}
    finally:
        conn.close()


def load_allowed_codes() -> Set[str]:
    db_codes = _load_codes_from_db()
    if db_codes:
        return db_codes

    _ensure_license_codes_from_project_dotenv()
    return _parse_codes_csv(os.getenv("OPENCLAW_LICENSE_CODES", ""))


def normalize_code(code: str) -> str:
    return re.sub(r"[\s\-]+", "", (code or "").strip()).upper()


def bind_or_verify(activation_code: str, machine_id: str) -> tuple[bool, str]:
    code_norm = normalize_code(activation_code)
    if not code_norm:
        return False, "激活码不能为空。"

    machine = (machine_id or "").strip()
    if not machine:
        return False, "机器码不能为空。"

    allowed = load_allowed_codes()
    conn = _connect()
    try:
        row: Optional[tuple] = conn.execute(
            "SELECT machine_id FROM license_bindings WHERE code_norm = ?",
            (code_norm,),
        ).fetchone()
        now = time.time()

        if row is not None:
            existing = row[0]
            if existing == machine:
                conn.execute(
                    "UPDATE license_bindings SET updated_at = ? WHERE code_norm = ?",
                    (now, code_norm),
                )
                conn.commit()
                return True, "本机已激活。"
            return False, "该激活码已被其他设备绑定，不能重复使用。"

        if not allowed:
            return False, "服务端未配置有效卡池，暂时无法校验新激活码。"

        if code_norm not in allowed:
            return False, "激活码无效，或不在当前有效卡池中。"

        conn.execute(
            "INSERT INTO license_bindings (code_norm, machine_id, updated_at) VALUES (?, ?, ?)",
            (code_norm, machine, now),
        )
        conn.commit()
        return True, "激活成功，当前激活码已绑定本机。"
    finally:
        conn.close()
