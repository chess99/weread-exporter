from weread_export.exporter import CapturePolicy


def test_capture_policy_assigns_monotonic_chapter_indexes():
    policy = CapturePolicy(catalog=["序", "第一章", "附录"])

    assert policy.chapter_index_for("序") == 1
    assert policy.chapter_index_for("第一章") == 2
    assert policy.chapter_index_for("附录") == 3
    assert policy.chapter_index_for("目录外小节") == 4


def test_capture_policy_detects_backward_title_without_book_specific_rules():
    policy = CapturePolicy(catalog=["序", "第一章", "第二章"])
    policy.chapter_index_for("序")
    policy.chapter_index_for("第一章")

    assert policy.is_backward_or_duplicate_chapter("序")
    assert not policy.is_backward_or_duplicate_chapter("第二章")


def test_capture_policy_completion_requires_last_catalog_title_and_stale_pages():
    policy = CapturePolicy(catalog=["序", "正文", "尾声"], stale_threshold=3)
    policy.chapter_index_for("正文")
    assert not policy.record_stale_page("正文")
    assert not policy.record_stale_page("正文")
    assert not policy.record_stale_page("正文")

    policy.chapter_index_for("尾声")
    assert not policy.record_stale_page("尾声")
    assert not policy.record_stale_page("尾声")
    assert policy.record_stale_page("尾声")

