from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from playwright.async_api import Page

from .utils import normalize_title


class LoginRequiredError(RuntimeError):
    pass


class PermissionBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReaderMetadata:
    title: str
    author: str
    catalog: list[str]


BLOCK_MARKERS = ("试读结束", "会员卡可读", "登录后获得", "购买", "去 App 阅读")


class ReaderNavigator:
    def __init__(self, page: Page) -> None:
        self.page = page

    async def open(self, reader_url: str) -> None:
        await self.page.goto(reader_url, wait_until="networkidle", timeout=45_000)
        await asyncio.sleep(2)

    async def ensure_logged_in(self) -> None:
        url = self.page.url.lower()
        text = await self.page.locator("body").inner_text(timeout=10_000)
        if "login" in url or "登录" in text and "首页" in text and "我的书架" in text:
            raise LoginRequiredError("WeRead login is required in the Playwright browser.")

    async def ensure_readable(self) -> None:
        text = await self.page.locator("body").inner_text(timeout=10_000)
        for marker in BLOCK_MARKERS:
            if marker in text:
                raise PermissionBlockedError(f"WeRead page is blocked by permission marker: {marker}")

    async def metadata(self) -> ReaderMetadata:
        data = await self.page.evaluate(
            r"""
() => {
  const title =
    document.querySelector('.readerCatalog_bookInfo_title_txt, .bookInfo_right_header_title')?.textContent?.trim()
    || document.title.replace(/\s*-\s*.*/, '').trim();
  const author =
    document.querySelector('.readerCatalog_bookInfo_author, .bookInfo_author a')?.textContent?.trim()
    || '';
  const catalog = Array.from(document.querySelectorAll('.readerCatalog_list_item'))
    .map((item) => item.textContent.trim())
    .filter(Boolean);
  return { title, author, catalog };
}
"""
        )
        catalog = [normalize_title(item) for item in list(data.get("catalog") or [])]
        if not catalog:
            catalog = [await self.current_chapter_title()]
        return ReaderMetadata(
            title=str(data.get("title") or "unknown"),
            author=str(data.get("author") or ""),
            catalog=catalog,
        )

    async def read_catalog(self) -> list[str]:
        await self._open_catalog()
        titles = await self.page.evaluate(
            r"""
() => Array.from(document.querySelectorAll('.readerCatalog_list_item'))
  .map((item) => item.textContent.trim())
  .filter(Boolean)
"""
        )
        return [normalize_title(item) for item in list(titles or [])]

    async def current_chapter_title(self) -> str:
        title = await self.page.evaluate(
            "() => document.querySelector('.renderTargetPageInfo_header_chapterTitle')?.textContent?.trim() || ''"
        )
        return normalize_title(str(title or "unknown"))

    async def goto_first_catalog_item(self, catalog: list[str] | None = None) -> str | None:
        titles = catalog or await self.read_catalog()
        normalized_titles = [normalize_title(title) for title in titles]
        for index, title in enumerate(normalized_titles):
            if not await self.goto_catalog_title(title):
                continue
            current = await self.current_chapter_title()
            if current in normalized_titles[index:]:
                return current
        return None

    async def probe_catalog_reachability(self, catalog: list[str]) -> dict[str, str | None]:
        result: dict[str, str | None] = {}
        for title in catalog:
            normalized = normalize_title(title)
            if not await self.goto_catalog_title(normalized):
                result[normalized] = None
                continue
            current = await self.current_chapter_title()
            result[normalized] = current or None
        return result

    async def goto_catalog_title(self, title: str) -> bool:
        if not title:
            return False
        try:
            await self._open_catalog()
            count = await self.page.locator(".readerCatalog_list_item").count()
            for index in range(count):
                item = self.page.locator(".readerCatalog_list_item").nth(index)
                text = normalize_title((await item.text_content() or "").strip())
                if text == normalize_title(title):
                    await item.click(timeout=5_000)
                    await asyncio.sleep(2)
                    return True
            return False
        except Exception:
            return False

    async def next_page(self) -> None:
        await self.page.keyboard.press("ArrowRight")
        await asyncio.sleep(1)

    async def _open_catalog(self) -> None:
        items = self.page.locator(".readerCatalog_list_item")
        if await items.count() > 0 and await items.first.is_visible():
            return
        await self.page.click("button.readerControls_item.catalog", timeout=5_000)
        await asyncio.sleep(1)
