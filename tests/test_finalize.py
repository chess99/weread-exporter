from pathlib import Path

from weread_export.capture import CanvasChar
from weread_export.checkpoint import CheckpointStore, Manifest
from weread_export.exporter import Finalizer
from weread_export.reconstruct import PageCapture, page_fingerprint


def _page(title: str, page_index: int, text: str, chapter_index: int) -> dict:
    capture = PageCapture(
        chapter_title=title,
        page_index=page_index,
        chars=[CanvasChar(text=char, x=index * 10, y=10, side="left") for index, char in enumerate(text)],
        images=[],
    )
    return {
        "chapterTitle": title,
        "chapterIndex": chapter_index,
        "pageIndex": page_index,
        "fingerprint": page_fingerprint(capture),
        "chars": [char.__dict__ for char in capture.chars],
        "images": [],
    }


def _spread(title: str, page_index: int, left: str, right: str, chapter_index: int) -> dict:
    chars = [
        *[CanvasChar(text=char, x=index * 10, y=10, side="left") for index, char in enumerate(left)],
        *[CanvasChar(text=char, x=index * 10, y=10, side="right") for index, char in enumerate(right)],
    ]
    capture = PageCapture(chapter_title=title, page_index=page_index, chars=chars, images=[])
    return {
        "chapterTitle": title,
        "chapterIndex": chapter_index,
        "pageIndex": page_index,
        "fingerprint": page_fingerprint(capture),
        "chars": [char.__dict__ for char in capture.chars],
        "images": [],
    }


def test_finalizer_keeps_same_title_chapters_separate_and_writes_merged_book(tmp_path: Path):
    store = CheckpointStore(tmp_path, "book123")
    manifest = Manifest.new(
        book_id="book123",
        reader_url="https://weread.qq.com/web/reader/book123",
        title="测试书",
        author="作者",
        catalog=["序", "附录", "附录"],
    )
    store.save_manifest(manifest)
    store.save_page(_page("附录", 1, "甲", 1))
    store.save_page(_page("附录", 2, "乙", 2))

    book_path = Finalizer(store).write_complete_book(manifest)

    chapter_files = sorted(store.chapters_dir.glob("*.md"))
    assert [path.name for path in chapter_files] == ["0001-附录.md", "0002-附录.md"]
    assert "甲" in chapter_files[0].read_text(encoding="utf-8")
    assert "乙" in chapter_files[1].read_text(encoding="utf-8")
    merged = book_path.read_text(encoding="utf-8")
    assert "# 测试书" in merged
    assert merged.count("# 附录") == 2


def test_checkpoint_store_rejects_duplicate_page_fingerprints(tmp_path: Path):
    store = CheckpointStore(tmp_path, "book123")
    payload = _page("第一章", 1, "内容", 1)

    assert store.save_page(payload) is not None
    assert store.save_page({**payload, "pageIndex": 2}) is None
    assert len(store.list_pages()) == 1


def test_checkpoint_store_appends_page_indexes_without_overwriting(tmp_path: Path):
    store = CheckpointStore(tmp_path, "book123")

    first = store.append_page(_page("第一章", 1, "甲", 1))
    second = store.append_page(_page("第一章", 1, "乙", 1))

    assert first.name == "000001.json"
    assert second.name == "000002.json"
    assert [page["pageIndex"] for page in store.list_pages()] == [1, 2]


def test_finalizer_splits_two_page_spread_when_next_chapter_starts_on_right(tmp_path: Path):
    store = CheckpointStore(tmp_path, "book123")
    manifest = Manifest.new(
        book_id="book123",
        reader_url="https://weread.qq.com/web/reader/book123",
        title="测试书",
        author="作者",
        catalog=["致谢", "引言"],
    )
    store.save_manifest(manifest)
    store.save_page(_spread("致谢", 1, "致谢上一章最后一句。", "引言新章节第一句。", 1))
    store.save_page(_page("引言", 2, "新章节第二句。", 2))

    Finalizer(store).write_complete_book(manifest)

    chapters = sorted(store.chapters_dir.glob("*.md"))
    first = chapters[0].read_text(encoding="utf-8")
    second = chapters[1].read_text(encoding="utf-8")
    assert "上一章最后一句" in first
    assert "新章节第一句" not in first
    assert "新章节第一句" in second
    assert "新章节第二句" in second


def test_complete_book_marks_captured_catalog_entries_reachable(tmp_path: Path):
    store = CheckpointStore(tmp_path, "book123")
    manifest = Manifest.new(
        book_id="book123",
        reader_url="https://weread.qq.com/web/reader/book123",
        title="测试书",
        author="作者",
        catalog=["引言"],
    )
    manifest.catalog_reachability = {"引言": None}
    manifest.skipped_catalog = ["引言"]
    store.save_manifest(manifest)
    store.save_page(_page("引言", 1, "引言正文。", 1))

    from weread_export.exporter import WeReadExporter

    WeReadExporter(output=tmp_path, profile=tmp_path / "profile")._write_chapters_and_book(store, manifest)

    saved = store.load_manifest()
    assert saved.catalog_reachability["引言"] == "引言"
    assert saved.skipped_catalog == []


def test_finalizer_splits_wrapped_chapter_heading_below_part_title(tmp_path: Path):
    store = CheckpointStore(tmp_path, "book123")
    manifest = Manifest.new("book123", "url", "书", "作者", ["第一篇 宏观", "第1章 普通人买A股"])
    payload = _page("第一篇 宏观", 1, "", 1)
    rows = [(10, "第一篇宏观"), (50, "第1章普通人"), (80, "买A股"), (120, "章节第一句。")]
    payload["chars"] = [
        CanvasChar(text=char, x=x * 10, y=y).__dict__
        for y, text in rows for x, char in enumerate(text)
    ]
    store.save_page(payload)
    store.save_page(_page("第一篇 宏观", 2, "章节第二句。", 1))

    chapters = Finalizer(store).load_page_captures(manifest.catalog)

    assert [title for _, title, _ in chapters] == manifest.catalog
    chapter_text = "".join(c.text for p in chapters[1][2] for c in p.chars)
    assert "章节第一句。" in chapter_text
    assert "章节第二句。" in chapter_text


def test_finalizer_ignores_resume_duplicate_with_changed_canvas_side(tmp_path: Path):
    store = CheckpointStore(tmp_path, "book123")
    first = _spread("章", 1, "甲。", "乙。", 1)
    second = _spread("章", 2, "甲。", "乙。", 1)
    for char in second["chars"]:
        char["side"] = "left"
    second["fingerprint"] = "legacy-different-side"
    store.save_page(first)
    store.save_page(second)

    chapters = Finalizer(store).load_page_captures(["章"])

    assert "".join(c.text for p in chapters[0][2] for c in p.chars) == "甲。乙。"


def test_finalizer_does_not_treat_body_word_as_earlier_catalog_heading(tmp_path: Path):
    store = CheckpointStore(tmp_path, "book123")
    store.save_page(_page("第1章", 1, "第1章正文。", 2))
    store.save_page(_page("第1章", 2, "说明这一现象的原因。", 2))

    chapters = Finalizer(store).load_page_captures(["说明", "第1章"])

    assert [title for _, title, _ in chapters] == ["第1章"]


def test_finalizer_requires_inner_heading_to_end_at_a_line_boundary(tmp_path: Path):
    store = CheckpointStore(tmp_path, "book123")
    payload = _page("章", 1, "", 1)
    payload["chars"] = [
        CanvasChar(text=char, x=x * 10, y=y).__dict__
        for y, text in [(10, "章"), (50, "说明这一现象的原因。")]
        for x, char in enumerate(text)
    ]
    store.save_page(payload)

    assert [title for _, title, _ in Finalizer(store).load_page_captures(["章", "说明"])] == ["章"]
