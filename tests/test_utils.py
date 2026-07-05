from weread_export.utils import parse_reader_target, safe_filename, wr_hash


def test_parse_reader_url_extracts_book_id_and_preserves_url():
    target = parse_reader_target(
        "https://weread.qq.com/web/reader/96b32ea0813aba18cg0113d0k6c8328f022d6c8349cc72d5"
    )

    assert target.book_id == "96b32ea0813aba18cg0113d0k6c8328f022d6c8349cc72d5"
    assert target.reader_url == (
        "https://weread.qq.com/web/reader/"
        "96b32ea0813aba18cg0113d0k6c8328f022d6c8349cc72d5"
    )


def test_parse_book_id_builds_reader_url():
    target = parse_reader_target("3300151161")

    assert target.book_id == "3300151161"
    assert target.reader_url == "https://weread.qq.com/web/reader/3300151161"


def test_wr_hash_matches_known_weread_chapter_hash_shape():
    assert wr_hash("45") == "6c8328f022d6c8349cc72d5"


def test_safe_filename_keeps_chinese_and_removes_windows_invalid_chars():
    assert safe_filename('第八章: 从"逃避"到自主?') == "第八章_ 从_逃避_到自主_"
