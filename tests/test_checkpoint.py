from pathlib import Path

from weread_export.checkpoint import CheckpointStore, Manifest


def test_checkpoint_store_writes_manifest_and_page_as_utf8(tmp_path: Path):
    store = CheckpointStore(tmp_path, "book123")
    manifest = Manifest.new(
        book_id="book123",
        reader_url="https://weread.qq.com/web/reader/book123",
        title="对工作说不",
        author="[英]大卫·弗雷恩",
        catalog=["引言 工作教条"],
    )

    store.save_manifest(manifest)
    store.save_page(
        {
            "chapterTitle": "引言 工作教条",
            "pageIndex": 1,
            "fingerprint": "abc",
            "text": "你好，世界",
        }
    )

    raw = (tmp_path / "book123" / "manifest.json").read_bytes()
    assert "对工作说不".encode("utf-8") in raw
    assert store.load_manifest().title == "对工作说不"
    assert store.list_pages()[0]["text"] == "你好，世界"


def test_resume_point_uses_last_completed_page_without_guessing_from_markdown(tmp_path: Path):
    store = CheckpointStore(tmp_path, "book123")
    manifest = Manifest.new(
        book_id="book123",
        reader_url="https://weread.qq.com/web/reader/book123",
        title="Book",
        author="Author",
        catalog=["A", "B"],
    )
    manifest.last_completed_chapter = "A"
    manifest.last_completed_page = 7
    store.save_manifest(manifest)

    resume = store.resume_point()

    assert resume.chapter_title == "A"
    assert resume.page_index == 7


def test_load_manifest_recovers_progress_decorated_titles_without_losing_checkpoint(tmp_path: Path):
    store = CheckpointStore(tmp_path, "book123")
    decorated = "第二篇 中观 判断行业周期当前读到 30%"
    clean = "第二篇 中观 判断行业周期"
    manifest = Manifest.new("book123", "https://weread.qq.com/web/reader/book123", "Book", "Author", [decorated, "第8章"])
    manifest.last_completed_chapter = decorated
    manifest.last_completed_page = 97
    manifest.catalog_reachability = {decorated: decorated}
    store.save_manifest(manifest)

    recovered = store.load_manifest()

    assert recovered.catalog == [clean, "第8章"]
    assert recovered.last_completed_chapter == clean
    assert recovered.last_completed_page == 97
    assert recovered.catalog_reachability == {clean: clean}

