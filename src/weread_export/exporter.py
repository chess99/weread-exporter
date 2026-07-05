from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

from .browser import BrowserSession
from .capture import read_canvas_chars, read_visible_images, reset_canvas_chars
from .checkpoint import CheckpointStore, Manifest
from .reader import LoginRequiredError, PermissionBlockedError, ReaderNavigator
from .reconstruct import PageCapture, page_fingerprint, reconstruct_markdown
from .utils import parse_reader_target, safe_filename


class DuplicatePageError(RuntimeError):
    pass


class WeReadExporter:
    def __init__(self, output: Path, profile: Path, *, headless: bool = False) -> None:
        self.output = Path(output)
        self.profile = Path(profile)
        self.headless = headless

    async def export(self, target_value: str, *, max_pages: int | None = None, overwrite: bool = False) -> Manifest:
        target = parse_reader_target(target_value)
        store = CheckpointStore(self.output, target.book_id)
        if overwrite and store.book_dir.exists():
            shutil.rmtree(store.book_dir)

        async with BrowserSession(self.profile, headless=self.headless) as session:
            page = await session.new_reader_page()
            navigator = ReaderNavigator(page)
            await navigator.open(target.reader_url)

            try:
                await navigator.ensure_logged_in()
                await navigator.ensure_readable()
            except LoginRequiredError as exc:
                manifest = Manifest.new(target.book_id, target.reader_url, "unknown", "", [])
                manifest.status = "blocked"
                manifest.block_reason = str(exc)
                store.save_manifest(manifest)
                return manifest
            except PermissionBlockedError as exc:
                metadata = await navigator.metadata()
                manifest = Manifest.new(target.book_id, target.reader_url, metadata.title, metadata.author, metadata.catalog)
                manifest.status = "blocked"
                manifest.block_reason = str(exc)
                store.save_manifest(manifest)
                return manifest

            metadata = await navigator.metadata()
            manifest = Manifest.new(target.book_id, target.reader_url, metadata.title, metadata.author, metadata.catalog)
            store.save_manifest(manifest)
            await navigator.goto_first_catalog_item()
            return await self._capture_pages(store, navigator, manifest, max_pages=max_pages)

    async def resume(self, book_id: str, *, max_pages: int | None = None) -> Manifest:
        store = CheckpointStore(self.output, book_id)
        manifest = store.load_manifest()
        async with BrowserSession(self.profile, headless=self.headless) as session:
            page = await session.new_reader_page()
            navigator = ReaderNavigator(page)
            await navigator.open(manifest.reader_url)
            await navigator.ensure_logged_in()
            await navigator.ensure_readable()
            return await self._capture_pages(store, navigator, manifest, max_pages=max_pages)

    async def _capture_pages(
        self,
        store: CheckpointStore,
        navigator: ReaderNavigator,
        manifest: Manifest,
        *,
        max_pages: int | None,
    ) -> Manifest:
        seen: set[str] = {str(page.get("fingerprint")) for page in store.list_pages()}
        recent_titles: list[str] = []
        captured = 0
        stale_count = 0

        while max_pages is None or captured < max_pages:
            await reset_canvas_chars(navigator.page)
            await navigator.next_page()
            chars = await read_canvas_chars(navigator.page)
            images = await read_visible_images(navigator.page)
            chapter_title = await navigator.current_chapter_title()
            page_index = manifest.last_completed_page + 1
            page_capture = PageCapture(chapter_title=chapter_title, page_index=page_index, chars=chars, images=images)
            fingerprint = page_fingerprint(page_capture)

            if fingerprint in seen:
                stale_count += 1
                if stale_count >= 3:
                    manifest.status = "complete"
                    store.save_manifest(manifest)
                    self._write_chapters_and_book(store, manifest)
                    return manifest
                continue
            stale_count = 0

            if recent_titles and chapter_title in recent_titles[:-1]:
                manifest.status = "failed"
                manifest.error = f"chapter title moved backward or repeated unexpectedly: {chapter_title}"
                store.save_manifest(manifest)
                raise DuplicatePageError(manifest.error)
            recent_titles.append(chapter_title)
            recent_titles = recent_titles[-8:]

            store.save_page(
                {
                    "chapterTitle": chapter_title,
                    "pageIndex": page_index,
                    "fingerprint": fingerprint,
                    "chars": [char.__dict__ for char in chars],
                    "images": images,
                }
            )
            seen.add(fingerprint)
            manifest.last_completed_chapter = chapter_title
            manifest.last_completed_page = page_index
            manifest.status = "running"
            store.save_manifest(manifest)
            captured += 1

        store.save_manifest(manifest)
        self._write_chapters(store, manifest)
        return manifest

    def _load_page_captures(self, store: CheckpointStore) -> dict[str, list[PageCapture]]:
        grouped: dict[str, list[PageCapture]] = defaultdict(list)
        for item in store.list_pages():
            title = str(item.get("chapterTitle") or "unknown")
            chars = [
                __import__("weread_export.capture", fromlist=["CanvasChar"]).CanvasChar(**char)
                for char in item.get("chars", [])
            ]
            grouped[title].append(
                PageCapture(
                    chapter_title=title,
                    page_index=int(item.get("pageIndex", 0)),
                    chars=chars,
                    images=list(item.get("images", [])),
                )
            )
        return grouped

    def _write_chapters(self, store: CheckpointStore, manifest: Manifest) -> list[Path]:
        store.ensure_dirs()
        paths: list[Path] = []
        grouped = self._load_page_captures(store)
        for index, (title, pages) in enumerate(grouped.items(), start=1):
            filename = f"{index:04d}-{safe_filename(title)}.md"
            path = store.chapters_dir / filename
            path.write_text(reconstruct_markdown(title, pages), encoding="utf-8")
            paths.append(path)
        return paths

    def _write_chapters_and_book(self, store: CheckpointStore, manifest: Manifest) -> Path:
        chapter_paths = self._write_chapters(store, manifest)
        title = safe_filename(manifest.title)
        book_path = store.book_dir / f"{title}.md"
        body = [f"# {manifest.title}", "", f"**{manifest.author}**".strip(), "", "---", ""]
        for path in chapter_paths:
            body.append(path.read_text(encoding="utf-8").rstrip())
            body.extend(["", "---", ""])
        book_path.write_text("\n".join(body).rstrip() + "\n", encoding="utf-8")
        return book_path

