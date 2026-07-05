from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from playwright.async_api import Page


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
        catalog = list(data.get("catalog") or [])
        if not catalog:
            catalog = [await self.current_chapter_title()]
        return ReaderMetadata(
            title=str(data.get("title") or "unknown"),
            author=str(data.get("author") or ""),
            catalog=catalog,
        )

    async def current_chapter_title(self) -> str:
        title = await self.page.evaluate(
            "() => document.querySelector('.renderTargetPageInfo_header_chapterTitle')?.textContent?.trim() || ''"
        )
        return str(title or "unknown")

    async def goto_first_catalog_item(self) -> None:
        try:
            await self.page.click("button.readerControls_item.catalog", timeout=5_000)
            await asyncio.sleep(1)
            first = self.page.locator(".readerCatalog_list_item").first
            await first.click(timeout=5_000)
            await asyncio.sleep(2)
            try:
                await self.page.keyboard.press("Escape")
            except Exception:
                pass
        except Exception:
            return

    async def next_page(self) -> None:
        await self.page.keyboard.press("ArrowRight")
        await asyncio.sleep(1)

