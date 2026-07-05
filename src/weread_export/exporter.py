from __future__ import annotations

import shutil
from pathlib import Path

from .browser import BrowserSession
from .capture import read_canvas_chars, read_visible_images, reset_canvas_chars
from .checkpoint import CheckpointStore, Manifest
from .reader import LoginRequiredError, PermissionBlockedError, ReaderNavigator
from .reconstruct import PageCapture, page_fingerprint, reconstruct_markdown
from .utils import normalize_title, parse_reader_target, safe_filename


class DuplicatePageError(RuntimeError):
    pass


async def prepare_current_page_capture(navigator: ReaderNavigator, title: str) -> bool:
    await reset_canvas_chars(navigator.page)
    return await navigator.goto_catalog_title(title)


def leading_catalog_title(chars: list[object], catalog: list[str]) -> str | None:
    text = "".join(getattr(char, "text") for char in sorted(chars, key=lambda char: (char.side, char.y, char.x)))
    compact_text = "".join(text.split())
    for title in catalog:
        compact_title = "".join(normalize_title(title).split())
        if compact_title and compact_text.startswith(compact_title):
            return normalize_title(title)
    return None


class CapturePolicy:
    def __init__(self, catalog: list[str], *, stale_threshold: int = 3) -> None:
        self.catalog = [normalize_title(item) for item in catalog if item]
        self.catalog_positions = {title: index + 1 for index, title in enumerate(self.catalog)}
        self.stale_threshold = stale_threshold
        self.max_seen_index = 0
        self.dynamic_positions: dict[str, int] = {}
        self.stale_count = 0
        self.stale_title: str | None = None

    def chapter_index_for(self, title: str) -> int:
        title = normalize_title(title)
        if title in self.catalog_positions:
            index = self.catalog_positions[title]
        else:
            if title not in self.dynamic_positions:
                self.dynamic_positions[title] = max(
                    [self.max_seen_index, len(self.catalog), *self.dynamic_positions.values(), 0]
                ) + 1
            index = self.dynamic_positions[title]
        self.max_seen_index = max(self.max_seen_index, index)
        return index

    def is_backward_or_duplicate_chapter(self, title: str) -> bool:
        title = normalize_title(title)
        index = self.catalog_positions.get(title) or self.dynamic_positions.get(title)
        if index is None:
            return False
        return index < self.max_seen_index

    def is_last_catalog_title(self, title: str) -> bool:
        title = normalize_title(title)
        return bool(self.catalog) and title == self.catalog[-1]

    def record_stale_page(self, title: str) -> bool:
        title = normalize_title(title)
        if self.stale_title != title:
            self.stale_title = title
            self.stale_count = 0
        self.stale_count += 1
        return self.is_last_catalog_title(title) and self.stale_count >= self.stale_threshold

    def record_new_page(self) -> None:
        self.stale_count = 0
        self.stale_title = None


class Finalizer:
    def __init__(self, store: CheckpointStore) -> None:
        self.store = store

    def load_page_captures(self, catalog: list[str] | None = None) -> list[tuple[int, str, list[PageCapture]]]:
        chapters: dict[tuple[int, str], list[PageCapture]] = {}
        order: list[tuple[int, str]] = []
        normalized_catalog = [normalize_title(title) for title in catalog or []]
        catalog_positions = {title: index + 1 for index, title in enumerate(normalized_catalog)}
        active_key: tuple[int, str] | None = None
        for item in self.store.list_pages():
            title = str(item.get("chapterTitle") or "unknown")
            chapter_index = int(item.get("chapterIndex") or len(order) + 1)
            chars = [
                __import__("weread_export.capture", fromlist=["CanvasChar"]).CanvasChar(**char)
                for char in item.get("chars", [])
            ]
            images = list(item.get("images", []))
            page_index = int(item.get("pageIndex", 0))
            for side_index, side in enumerate(("left", "right")):
                side_chars = [char for char in chars if char.side == side]
                side_images = self._images_for_side(images, side)
                if not side_chars and not side_images:
                    continue
                detected_title = self._detect_catalog_title(side_chars, normalized_catalog)
                if detected_title:
                    key = (catalog_positions.get(detected_title, chapter_index), detected_title)
                elif active_key and normalize_title(title) == normalize_title(active_key[1]) and chapter_index > active_key[0]:
                    key = (chapter_index, title)
                elif active_key:
                    key = active_key
                else:
                    key = (chapter_index, title)
                active_key = key
                if key not in chapters:
                    chapters[key] = []
                    order.append(key)
                chapters[key].append(
                    PageCapture(
                        chapter_title=key[1],
                        page_index=page_index * 2 + side_index,
                        chars=side_chars,
                        images=side_images,
                    )
                )
        return [(index, title, chapters[(index, title)]) for index, title in order]

    def _detect_catalog_title(self, chars: list[object], catalog: list[str]) -> str | None:
        text = "".join(getattr(char, "text") for char in sorted(chars, key=lambda char: (char.y, char.x)))
        compact_text = "".join(text.split())
        for title in catalog:
            compact_title = "".join(title.split())
            if compact_title and compact_text.startswith(compact_title):
                return title
        return None

    def _images_for_side(self, images: list[dict], side: str) -> list[dict]:
        if not images:
            return []
        midpoint = 600
        return [
            image
            for image in images
            if ("left" not in image)
            or (side == "left" and int(image.get("left", 0)) < midpoint)
            or (side == "right" and int(image.get("left", 0)) >= midpoint)
        ]

    def write_chapters(self, manifest: Manifest | None = None) -> list[Path]:
        self.store.ensure_dirs()
        for old_path in self.store.chapters_dir.glob("*.md"):
            old_path.unlink()
        paths: list[Path] = []
        catalog = manifest.catalog if manifest else None
        for sequence, (_chapter_index, title, pages) in enumerate(self.load_page_captures(catalog), start=1):
            filename = f"{sequence:04d}-{safe_filename(title)}.md"
            path = self.store.chapters_dir / filename
            path.write_text(reconstruct_markdown(title, pages), encoding="utf-8")
            paths.append(path)
        return paths

    def write_complete_book(self, manifest: Manifest) -> Path:
        chapter_paths = self.write_chapters(manifest)
        title = safe_filename(manifest.title)
        book_path = self.store.book_dir / f"{title}.md"
        body = [f"# {manifest.title}", "", f"**{manifest.author}**".strip(), "", "---", ""]
        for path in chapter_paths:
            body.append(path.read_text(encoding="utf-8").rstrip())
            body.extend(["", "---", ""])
        book_path.write_text("\n".join(body).rstrip() + "\n", encoding="utf-8")
        return book_path


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
            catalog = await navigator.read_catalog()
            if catalog:
                metadata = type(metadata)(title=metadata.title, author=metadata.author, catalog=catalog)
            manifest = Manifest.new(target.book_id, target.reader_url, metadata.title, metadata.author, metadata.catalog)
            store.save_manifest(manifest)
            manifest.catalog_reachability = await navigator.probe_catalog_reachability(metadata.catalog)
            start_title = await navigator.goto_first_catalog_item(metadata.catalog)
            if not start_title:
                manifest.status = "failed"
                manifest.error = "failed to navigate to any catalog item"
                store.save_manifest(manifest)
                return manifest
            if start_title in metadata.catalog:
                manifest.skipped_catalog = [
                    title
                    for title in metadata.catalog[: metadata.catalog.index(start_title)]
                    if manifest.catalog_reachability.get(title) != title
                ]
                store.save_manifest(manifest)
            if not await prepare_current_page_capture(navigator, start_title):
                manifest.status = "failed"
                manifest.error = f"failed to prepare capture for catalog item: {start_title}"
                store.save_manifest(manifest)
                return manifest
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
            if manifest.last_completed_chapter:
                await prepare_current_page_capture(navigator, manifest.last_completed_chapter)
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
        policy = CapturePolicy(manifest.catalog)
        for item in store.list_pages():
            title = str(item.get("chapterTitle") or "")
            if title:
                policy.chapter_index_for(title)
        captured = 0

        while max_pages is None or captured < max_pages:
            chars = await read_canvas_chars(navigator.page)
            images = await read_visible_images(navigator.page)
            chapter_title = await navigator.current_chapter_title()
            detected_title = leading_catalog_title(chars, manifest.catalog)
            current_position = policy.catalog_positions.get(normalize_title(chapter_title))
            detected_position = policy.catalog_positions.get(detected_title or "")
            if detected_position and current_position and detected_position < current_position:
                if await prepare_current_page_capture(navigator, chapter_title):
                    chars = await read_canvas_chars(navigator.page)
                    images = await read_visible_images(navigator.page)
                    chapter_title = await navigator.current_chapter_title()
            page_index = manifest.last_completed_page + 1
            page_capture = PageCapture(chapter_title=chapter_title, page_index=page_index, chars=chars, images=images)
            fingerprint = page_fingerprint(page_capture)

            if fingerprint in seen:
                if policy.record_stale_page(chapter_title):
                    manifest.status = "complete"
                    store.save_manifest(manifest)
                    self._write_chapters_and_book(store, manifest)
                    return manifest
                await reset_canvas_chars(navigator.page)
                await navigator.next_page()
                continue

            if policy.is_backward_or_duplicate_chapter(chapter_title):
                manifest.status = "failed"
                manifest.error = f"chapter title moved backward or repeated unexpectedly: {chapter_title}"
                store.save_manifest(manifest)
                raise DuplicatePageError(manifest.error)
            chapter_index = policy.chapter_index_for(chapter_title)
            policy.record_new_page()

            saved = store.append_page(
                {
                    "chapterTitle": chapter_title,
                    "chapterIndex": chapter_index,
                    "fingerprint": fingerprint,
                    "chars": [char.__dict__ for char in chars],
                    "images": images,
                }
            )
            if saved is None:
                continue
            seen.add(fingerprint)
            manifest.last_completed_chapter = chapter_title
            manifest.last_completed_page = len(store.list_pages())
            manifest.status = "running"
            store.save_manifest(manifest)
            captured += 1
            if max_pages is not None and captured >= max_pages:
                break
            await reset_canvas_chars(navigator.page)
            await navigator.next_page()

        store.save_manifest(manifest)
        Finalizer(store).write_chapters(manifest)
        return manifest

    def _write_chapters_and_book(self, store: CheckpointStore, manifest: Manifest) -> Path:
        page_titles = {str(page.get("chapterTitle") or "") for page in store.list_pages()}
        skipped = set(manifest.skipped_catalog)
        for title in manifest.catalog:
            if title in page_titles:
                manifest.catalog_reachability[title] = title
                continue
            if manifest.catalog_reachability.get(title) != title:
                skipped.add(title)
        manifest.skipped_catalog = [title for title in manifest.catalog if title in skipped]
        store.save_manifest(manifest)
        return Finalizer(store).write_complete_book(manifest)
