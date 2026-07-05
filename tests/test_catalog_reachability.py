from pathlib import Path

from weread_export.checkpoint import CheckpointStore, Manifest
from weread_export.exporter import WeReadExporter


def test_complete_book_records_missing_unreachable_catalog_items(tmp_path: Path):
    store = CheckpointStore(tmp_path, "book123")
    manifest = Manifest.new(
        book_id="book123",
        reader_url="https://weread.qq.com/web/reader/book123",
        title="测试书",
        author="作者",
        catalog=["扉页", "版权信息", "献词"],
    )
    manifest.status = "complete"
    manifest.catalog_reachability = {
        "扉页": "版权信息",
        "版权信息": "版权信息",
        "献词": "版权信息",
    }
    store.save_manifest(manifest)
    store.save_page(
        {
            "chapterTitle": "版权信息",
            "chapterIndex": 2,
            "pageIndex": 1,
            "fingerprint": "abc",
            "chars": [],
            "images": [],
        }
    )

    WeReadExporter(tmp_path / "unused-output", tmp_path / "unused-profile")._write_chapters_and_book(store, manifest)

    saved = store.load_manifest()
    assert saved.skipped_catalog == ["扉页", "献词"]

