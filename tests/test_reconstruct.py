from weread_export.capture import CanvasChar
from weread_export.reconstruct import PageCapture, page_fingerprint, reconstruct_markdown


def test_reconstruct_orders_canvas_chars_by_y_then_x_and_merges_lines():
    page = PageCapture(
        chapter_title="引言 工作教条",
        page_index=1,
        chars=[
            CanvasChar(text="界", x=30, y=30, side="left"),
            CanvasChar(text="世", x=10, y=30, side="left"),
            CanvasChar(text="你", x=10, y=10, side="left"),
            CanvasChar(text="好", x=30, y=10, side="left"),
        ],
        images=[],
    )

    markdown = reconstruct_markdown("引言 工作教条", [page])

    assert markdown == "# 引言 工作教条\n\n你好世界\n"


def test_reconstruct_inserts_visible_images_between_text_blocks():
    page = PageCapture(
        chapter_title="版权信息",
        page_index=1,
        chars=[CanvasChar(text="版", x=10, y=10, side="left")],
        images=[{"src": "https://res.weread.qq.com/wrepub/example.jpg", "top": 20}],
    )

    markdown = reconstruct_markdown("版权信息", [page])

    assert "版" in markdown
    assert "![](https://res.weread.qq.com/wrepub/example.jpg)" in markdown


def test_page_fingerprint_is_stable_for_duplicate_pages():
    page = PageCapture(
        chapter_title="重复页",
        page_index=3,
        chars=[CanvasChar(text="A", x=1, y=1, side="left")],
        images=[],
    )

    assert page_fingerprint(page) == page_fingerprint(page)

