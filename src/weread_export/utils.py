from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


READER_ROOT = "https://weread.qq.com/web/reader/"
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class ReaderTarget:
    book_id: str
    reader_url: str


def parse_reader_target(value: str) -> ReaderTarget:
    raw = value.strip().rstrip("/")
    if not raw:
        raise ValueError("reader URL or book id is required")
    if "weread.qq.com" in raw:
        match = re.search(r"/web/reader/([^/?#]+)", raw)
        if not match:
            raise ValueError(f"not a WeRead reader URL: {value}")
        book_id = match.group(1)
        return ReaderTarget(book_id=book_id, reader_url=f"{READER_ROOT}{book_id}")
    return ReaderTarget(book_id=raw, reader_url=f"{READER_ROOT}{raw}")


def safe_filename(value: str, max_length: int = 80) -> str:
    name = INVALID_FILENAME_CHARS.sub("_", value).strip()
    name = re.sub(r"\s+", " ", name)
    name = name.rstrip(". ")
    if not name:
        name = "untitled"
    return name[:max_length]


def md5(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.md5(value).hexdigest()


def wr_hash(value: str) -> str:
    hash_str = md5(value)
    result = hash_str[:3] + "32" + hash_str[-2:]
    chunks: list[str] = []
    for index in range(0, len(value), 9):
        chunks.append(f"{int(value[index:min(index + 9, len(value))]):x}")
    for index, chunk in enumerate(chunks):
        size = f"{len(chunk):x}"
        if len(size) == 1:
            size = "0" + size
        result += size + chunk
        if index < len(chunks) - 1:
            result += "g"
    if len(result) < 20:
        result += hash_str[: 20 - len(result)]
    result += hashlib.md5(result.encode("utf-8")).hexdigest()[:3]
    return result

