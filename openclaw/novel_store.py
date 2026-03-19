"""
小说项目 JSON 存储
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Chapter:
    """章节"""
    id: str
    order: int
    title: str
    content: str
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Chapter:
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            order=d.get("order", 0),
            title=d.get("title", ""),
            content=d.get("content", ""),
            summary=d.get("summary", ""),
        )


@dataclass
class Novel:
    """小说项目"""
    id: str
    title: str
    genre: str  # short | long
    synopsis: str
    characters: str
    chapters: list[Chapter] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "genre": self.genre,
            "synopsis": self.synopsis,
            "characters": self.characters,
            "chapters": [c.to_dict() for c in self.chapters],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Novel:
        chapters = [Chapter.from_dict(c) for c in d.get("chapters", [])]
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            title=d.get("title", "未命名"),
            genre=d.get("genre", "short"),
            synopsis=d.get("synopsis", ""),
            characters=d.get("characters", ""),
            chapters=chapters,
        )


def _store_dir() -> Path:
    """存储目录"""
    if Path.home().joinpath(".openclaw").exists():
        base = Path.home() / ".openclaw"
    else:
        base = Path.home() / ".openclaw"
    base.mkdir(parents=True, exist_ok=True)
    novels_dir = base / "novels"
    novels_dir.mkdir(parents=True, exist_ok=True)
    return novels_dir


def list_novels() -> list[Novel]:
    """列出所有小说"""
    store = _store_dir()
    novels = []
    for f in store.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            novels.append(Novel.from_dict(data))
        except Exception:
            continue
    return sorted(novels, key=lambda n: n.title)


def load_novel(novel_id: str) -> Optional[Novel]:
    """加载小说"""
    path = _store_dir() / f"{novel_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Novel.from_dict(data)
    except Exception:
        return None


def save_novel(novel: Novel) -> None:
    """保存小说"""
    path = _store_dir() / f"{novel.id}.json"
    path.write_text(json.dumps(novel.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def create_novel(title: str, genre: str = "short", synopsis: str = "", characters: str = "") -> Novel:
    """创建新小说"""
    novel = Novel(
        id=str(uuid.uuid4()),
        title=title,
        genre=genre,
        synopsis=synopsis,
        characters=characters,
        chapters=[],
    )
    save_novel(novel)
    return novel


def delete_novel(novel_id: str) -> bool:
    """删除小说"""
    path = _store_dir() / f"{novel_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False
