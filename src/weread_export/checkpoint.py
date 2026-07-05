from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


Status = Literal["running", "complete", "blocked", "failed"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Manifest:
    book_id: str
    reader_url: str
    title: str
    author: str
    catalog: list[str]
    status: Status
    last_completed_chapter: str | None
    last_completed_page: int
    created_at: str
    updated_at: str
    block_reason: str | None = None
    error: str | None = None

    @classmethod
    def new(cls, book_id: str, reader_url: str, title: str, author: str, catalog: list[str]) -> "Manifest":
        now = utc_now()
        return cls(
            book_id=book_id,
            reader_url=reader_url,
            title=title,
            author=author,
            catalog=catalog,
            status="running",
            last_completed_chapter=None,
            last_completed_page=0,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Manifest":
        normalized = {
            "book_id": data.get("book_id", data.get("bookId", "")),
            "reader_url": data.get("reader_url", data.get("readerUrl", "")),
            "title": data.get("title", ""),
            "author": data.get("author", ""),
            "catalog": data.get("catalog", []),
            "status": data.get("status", "running"),
            "last_completed_chapter": data.get("last_completed_chapter", data.get("lastCompletedChapter")),
            "last_completed_page": data.get("last_completed_page", data.get("lastCompletedPage", 0)),
            "created_at": data.get("created_at", data.get("createdAt", utc_now())),
            "updated_at": data.get("updated_at", data.get("updatedAt", utc_now())),
            "block_reason": data.get("block_reason", data.get("blockReason")),
            "error": data.get("error"),
        }
        return cls(**normalized)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "bookId": self.book_id,
            "readerUrl": self.reader_url,
            "title": self.title,
            "author": self.author,
            "catalog": self.catalog,
            "status": self.status,
            "lastCompletedChapter": self.last_completed_chapter,
            "lastCompletedPage": self.last_completed_page,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "blockReason": self.block_reason,
            "error": self.error,
        }


@dataclass(frozen=True)
class ResumePoint:
    chapter_title: str | None
    page_index: int


@dataclass
class CheckpointStore:
    output_root: Path
    book_id: str
    book_dir: Path = field(init=False)
    pages_dir: Path = field(init=False)
    chapters_dir: Path = field(init=False)
    images_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.output_root = Path(self.output_root)
        self.book_dir = self.output_root / self.book_id
        self.pages_dir = self.book_dir / "pages"
        self.chapters_dir = self.book_dir / "chapters"
        self.images_dir = self.book_dir / "images"

    @property
    def manifest_path(self) -> Path:
        return self.book_dir / "manifest.json"

    def ensure_dirs(self) -> None:
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.chapters_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def save_manifest(self, manifest: Manifest) -> None:
        self.ensure_dirs()
        manifest.updated_at = utc_now()
        self.manifest_path.write_text(
            json.dumps(manifest.to_json_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_manifest(self) -> Manifest:
        return Manifest.from_dict(json.loads(self.manifest_path.read_text(encoding="utf-8")))

    def save_page(self, payload: dict[str, Any]) -> Path:
        self.ensure_dirs()
        index = int(payload.get("pageIndex") or payload.get("page_index") or 0)
        filename = f"{index:06d}.json"
        path = self.pages_dir / filename
        fingerprint = payload.get("fingerprint")
        if fingerprint and any(page.get("fingerprint") == fingerprint for page in self.list_pages()):
            return None
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def append_page(self, payload: dict[str, Any]) -> Path | None:
        self.ensure_dirs()
        fingerprint = payload.get("fingerprint")
        existing = self.list_pages()
        if fingerprint and any(page.get("fingerprint") == fingerprint for page in existing):
            return None
        next_index = len(existing) + 1
        payload = dict(payload)
        payload["pageIndex"] = next_index
        path = self.pages_dir / f"{next_index:06d}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def list_pages(self) -> list[dict[str, Any]]:
        if not self.pages_dir.exists():
            return []
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self.pages_dir.glob("*.json"))
        ]

    def resume_point(self) -> ResumePoint:
        manifest = self.load_manifest()
        return ResumePoint(
            chapter_title=manifest.last_completed_chapter,
            page_index=manifest.last_completed_page,
        )
