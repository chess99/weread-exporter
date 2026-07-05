from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .capture import CanvasChar


SENTENCE_END = set("。！？；：”’）》】」』…")


@dataclass(frozen=True)
class PageCapture:
    chapter_title: str
    page_index: int
    chars: list[CanvasChar]
    images: list[dict[str, Any]]


def chars_to_lines(chars: list[CanvasChar]) -> list[tuple[int, str]]:
    rows: dict[tuple[str, int], list[CanvasChar]] = {}
    for char in chars:
        if not char.text.strip():
            continue
        key = (char.side, round(char.y / 3) * 3)
        rows.setdefault(key, []).append(char)

    ordered: list[tuple[int, str]] = []
    side_rank = {"left": 0, "right": 1}
    for (side, y), row in sorted(rows.items(), key=lambda item: (side_rank.get(item[0][0], 9), item[0][1])):
        text = "".join(item.text for item in sorted(row, key=lambda item: item.x)).strip()
        if text:
            ordered.append((y, text))
    return ordered


def _merge_lines(lines: list[str], chapter_title: str) -> list[str]:
    merged: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped == chapter_title:
            continue
        if merged and merged[-1] and merged[-1][-1] not in SENTENCE_END:
            merged[-1] += stripped
        else:
            merged.append(stripped)
    return merged


def reconstruct_markdown(chapter_title: str, pages: list[PageCapture]) -> str:
    blocks: list[str] = [f"# {chapter_title}"]
    for page in pages:
        items: list[tuple[int, str, str]] = []
        for y, text in chars_to_lines(page.chars):
            items.append((y, "text", text))
        for image in page.images:
            src = str(image.get("src") or "")
            if src:
                items.append((int(image.get("top", 0)), "image", src))
        para_lines: list[str] = []
        for _, kind, value in sorted(items, key=lambda item: item[0]):
            if kind == "text":
                para_lines.append(value)
                continue
            for paragraph in _merge_lines(para_lines, chapter_title):
                blocks.append(paragraph)
            para_lines = []
            blocks.append(f"![]({value})")
        for paragraph in _merge_lines(para_lines, chapter_title):
            blocks.append(paragraph)
    return "\n\n".join(blocks).rstrip() + "\n"


def page_fingerprint(page: PageCapture) -> str:
    payload = "|".join(f"{char.side}:{round(char.x)}:{round(char.y)}:{char.text}" for char in page.chars)
    payload += "|" + "|".join(str(image.get("src", "")) for image in page.images)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

