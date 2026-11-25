import pytest

from app.services.record_selector import parse_record_selection


def test_single_and_comma_list():
    assert parse_record_selection("1,2,3", 10) == [1, 2, 3]
    assert parse_record_selection(" 3 , 1 , 2 ", 10) == [3, 1, 2]


def test_ranges_and_mixed():
    assert parse_record_selection("1-5", 10) == [1, 2, 3, 4, 5]
    assert parse_record_selection("1,3-6", 10) == [1, 3, 4, 5, 6]


def test_deduplicates_preserving_order():
    assert parse_record_selection("1,2-4,3,1", 10) == [1, 2, 3, 4]


def test_all_keyword():
    assert parse_record_selection("all", 5) == [1, 2, 3, 4, 5]
    assert parse_record_selection(" ALL ", 3) == [1, 2, 3]


def test_errors_on_empty_and_bad_syntax():
    with pytest.raises(ValueError, match="enter record numbers"):
        parse_record_selection("", 10)
    with pytest.raises(ValueError, match="extra commas"):
        parse_record_selection("1,,2", 10)
    with pytest.raises(ValueError, match="Invalid selection"):
        parse_record_selection("abc", 10)
    with pytest.raises(ValueError, match="Invalid range"):
        parse_record_selection("5-2", 10)


def test_errors_on_out_of_range():
    with pytest.raises(ValueError, match="out of range"):
        parse_record_selection("0", 10)
    with pytest.raises(ValueError, match="out of range"):
        parse_record_selection("99", 52)
    with pytest.raises(ValueError, match="out of range"):
        parse_record_selection("1-12", 10)


def test_errors_on_max_records_limit():
    with pytest.raises(ValueError, match="Maximum allowed"):
        parse_record_selection("all", 201, max_records=200)
    with pytest.raises(ValueError, match="Maximum allowed"):
        parse_record_selection("1-201", 250, max_records=200)


def test_errors_on_empty_sheet():
    with pytest.raises(ValueError, match="no data records"):
        parse_record_selection("1", 0)
