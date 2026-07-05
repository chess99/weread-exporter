import pytest

from weread_export.reader import ReaderNavigator


class FakeLocator:
    def __init__(self, texts):
        self.texts = texts
        self.index = None

    @property
    def first(self):
        return FakeItem(self, 0)

    def nth(self, index):
        return FakeItem(self, index)

    async def count(self):
        return len(self.texts)


class FakeItem:
    def __init__(self, locator, index):
        self.locator = locator
        self.index = index

    async def text_content(self):
        return self.locator.texts[self.index]

    async def click(self, timeout=0):
        self.locator.index = self.index

    async def is_visible(self):
        return True


class FakePage:
    def __init__(self, titles, current_after_click=None):
        self.catalog = FakeLocator(titles)
        self.clicked_selectors = []
        self.keyboard = self
        self.current_after_click = current_after_click or {}

    def locator(self, selector):
        assert selector == ".readerCatalog_list_item"
        return self.catalog

    async def click(self, selector, timeout=0):
        self.clicked_selectors.append(selector)

    async def press(self, key):
        pass

    async def evaluate(self, script):
        if self.catalog.index is None:
            return ""
        clicked = self.catalog.texts[self.catalog.index]
        return self.current_after_click.get(clicked, clicked)


@pytest.mark.asyncio
async def test_goto_first_catalog_item_clicks_first_matching_catalog_entry():
    page = FakePage(["扉页", "版权信息", "引言 工作教条"])
    navigator = ReaderNavigator(page)

    assert await navigator.goto_first_catalog_item(["扉页", "版权信息"]) == "扉页"

    assert page.catalog.index == 0


@pytest.mark.asyncio
async def test_goto_catalog_title_matches_normalized_title():
    page = FakePage(["引言 工作教条+书签"])
    navigator = ReaderNavigator(page)

    assert await navigator.goto_catalog_title("引言 工作教条") is True

    assert page.catalog.index == 0


@pytest.mark.asyncio
async def test_goto_first_catalog_item_falls_back_to_first_reachable_title():
    page = FakePage(
        ["扉页", "版权信息", "引言 工作教条"],
        current_after_click={"扉页": "版权信息"},
    )
    navigator = ReaderNavigator(page)

    assert await navigator.goto_first_catalog_item(["扉页", "版权信息", "引言 工作教条"]) == "版权信息"

    assert page.catalog.index == 0
