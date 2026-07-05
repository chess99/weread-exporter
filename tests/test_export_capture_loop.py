from pathlib import Path

import pytest

from weread_export.capture import CanvasChar
from weread_export.checkpoint import CheckpointStore, Manifest
from weread_export.exporter import WeReadExporter, prepare_current_page_capture


class FakeNavigator:
    def __init__(self) -> None:
        self.page = object()
        self.position = 0
        self.titles = ["A", "A", "B"]

    async def next_page(self) -> None:
        self.position = min(self.position + 1, len(self.titles) - 1)

    async def current_chapter_title(self) -> str:
        return self.titles[self.position]


class RecoveringNavigator(FakeNavigator):
    def __init__(self) -> None:
        super().__init__()
        self.titles = ["B", "B"]
        self.goto_calls: list[str] = []

    async def goto_catalog_title(self, title: str) -> bool:
        self.goto_calls.append(title)
        return True


class FakeCatalogNavigator:
    def __init__(self) -> None:
        self.page = object()
        self.calls: list[tuple[str, str | None]] = []

    async def goto_catalog_title(self, title: str) -> bool:
        self.calls.append(("goto", title))
        return True


@pytest.mark.asyncio
async def test_capture_loop_saves_current_page_before_turning(monkeypatch, tmp_path: Path):
    navigator = FakeNavigator()

    async def fake_reset(_page):
        return None

    async def fake_read_chars(_page):
        text = ["A1", "A2", "B1"][navigator.position]
        return [CanvasChar(text=char, x=index * 10, y=10, side="left") for index, char in enumerate(text)]

    async def fake_read_images(_page):
        return []

    monkeypatch.setattr("weread_export.exporter.reset_canvas_chars", fake_reset)
    monkeypatch.setattr("weread_export.exporter.read_canvas_chars", fake_read_chars)
    monkeypatch.setattr("weread_export.exporter.read_visible_images", fake_read_images)

    store = CheckpointStore(tmp_path, "book123")
    manifest = Manifest.new("book123", "https://weread.qq.com/web/reader/book123", "Book", "Author", ["A", "B"])

    exporter = WeReadExporter(output=tmp_path, profile=tmp_path / "profile")
    await exporter._capture_pages(store, navigator, manifest, max_pages=2)

    saved_text = ["".join(char["text"] for char in page["chars"]) for page in store.list_pages()]
    assert saved_text == ["A1", "A2"]


@pytest.mark.asyncio
async def test_prepare_current_page_capture_clears_probe_buffer_before_reopening(monkeypatch):
    navigator = FakeCatalogNavigator()

    async def fake_reset(page):
        assert page is navigator.page
        navigator.calls.append(("reset", None))

    monkeypatch.setattr("weread_export.exporter.reset_canvas_chars", fake_reset)

    assert await prepare_current_page_capture(navigator, "引言") is True
    assert navigator.calls == [("reset", None), ("goto", "引言")]


@pytest.mark.asyncio
async def test_capture_loop_recovers_when_canvas_still_shows_earlier_chapter(monkeypatch, tmp_path: Path):
    navigator = RecoveringNavigator()
    reads = 0

    async def fake_reset(_page):
        return None

    async def fake_read_chars(_page):
        nonlocal reads
        reads += 1
        text = "A old page" if reads == 1 else "B fresh page"
        return [CanvasChar(text=char, x=index * 10, y=10, side="left") for index, char in enumerate(text)]

    async def fake_read_images(_page):
        return []

    monkeypatch.setattr("weread_export.exporter.reset_canvas_chars", fake_reset)
    monkeypatch.setattr("weread_export.exporter.read_canvas_chars", fake_read_chars)
    monkeypatch.setattr("weread_export.exporter.read_visible_images", fake_read_images)

    store = CheckpointStore(tmp_path, "book123")
    manifest = Manifest.new("book123", "https://weread.qq.com/web/reader/book123", "Book", "Author", ["A", "B"])

    exporter = WeReadExporter(output=tmp_path, profile=tmp_path / "profile")
    await exporter._capture_pages(store, navigator, manifest, max_pages=1)

    saved_text = ["".join(char["text"] for char in page["chars"]) for page in store.list_pages()]
    assert saved_text == ["B fresh page"]
    assert navigator.goto_calls == ["B"]
