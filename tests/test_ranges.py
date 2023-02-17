import pytest

from blacksheep.ranges import InvalidRangeValue, Range, RangePart


@pytest.mark.parametrize(
    "range_a,range_b,equals",
    [
        [
            Range("bytes", [RangePart(100, None)]),
            Range("bytes", [RangePart(100, None)]),
            True,
        ],
        [
            Range("bytes", [RangePart(100, None)]),
            Range("bytes", [RangePart(None, 100)]),
            False,
        ],
        [
            Range("bytes", [RangePart(100, 200), RangePart(400, 600)]),
            Range("bytes", [RangePart(100, 200), RangePart(400, 600)]),
            True,
        ],
        [
            Range("bytes", [RangePart(100, 200), RangePart(400, 600)]),
            Range("bytes", [RangePart(100, 200), RangePart(400, 650)]),
            False,
        ],
        [
            Range(
                "bytes", [RangePart(100, 200), RangePart(400, 600), RangePart(300, 500)]
            ),
            Range(
                "bytes", [RangePart(100, 200), RangePart(400, 600), RangePart(300, 500)]
            ),
            True,
        ],
    ],
)
def test_range_equality(range_a, range_b, equals):
    assert (range_a == range_b) is equals


@pytest.mark.parametrize(
    "value,expected_value",
    [
        [Range("bytes", [RangePart(100, None)]), False],
        [Range("bytes", [RangePart(100, 200), RangePart(400, 600)]), True],
        [
            Range(
                "bytes", [RangePart(100, 200), RangePart(400, 600), RangePart(300, 500)]
            ),
            True,
        ],
    ],
)
def test_range_is_multipart(value: Range, expected_value: bool):
    assert value.is_multipart == expected_value


@pytest.mark.parametrize(
    "value,expected_range",
    [
        (b"bytes=100-", Range("bytes", [RangePart(100, None)])),
        (b"bytes=-120", Range("bytes", [RangePart(None, 120)])),
        ("bytes=-120", Range("bytes", [RangePart(None, 120)])),
        (
            "bytes=100-200, 400-600, 300-500",
            Range(
                "bytes", [RangePart(100, 200), RangePart(400, 600), RangePart(300, 500)]
            ),
        ),
        (
            "bytes=100-200,400-600,300-500",
            Range(
                "bytes", [RangePart(100, 200), RangePart(400, 600), RangePart(300, 500)]
            ),
        ),
        (
            "bytes=1200-, -100",
            Range("bytes", [RangePart(1200, None), RangePart(None, 100)]),
        ),
    ],
)
def test_parse_range(value, expected_range):
    parsed_range = Range.parse(value)
    assert parsed_range == expected_range


@pytest.mark.parametrize(
    "value,item",
    [
        ("bytes=100-", Range("bytes", [RangePart(100, None)])),
        ("bytes=-120", Range("bytes", [RangePart(None, 120)])),
        ("bytes=-120", Range("bytes", [RangePart(None, 120)])),
        (
            "bytes=100-200, 400-600, 300-500",
            Range(
                "bytes", [RangePart(100, 200), RangePart(400, 600), RangePart(300, 500)]
            ),
        ),
        (
            "bytes=1200-, -100",
            Range("bytes", [RangePart(1200, None), RangePart(None, 100)]),
        ),
    ],
)
def test_range_repr(value, item):
    assert repr(item) == f"<Range {value}>"


@pytest.mark.parametrize(
    "invalid_value",
    [
        "1000",
        "100-200",
        "bytes=10",
        "bytes=100--200",
        "bytes=100AA, 400-600, 300-500",
        "bytes=100-200, 400-600, 300-A0",
        "bytes=100-AA, 400-600, 300-500",
    ],
)
def test_raise_for_invalid_value(invalid_value):
    with pytest.raises(InvalidRangeValue):
        Range.parse(invalid_value)


@pytest.mark.parametrize(
    "item", [Range("bytes", [RangePart(100, None)]), RangePart(100, None)]
)
def test_range_eq_not_implemented(item):
    value = item.__eq__(True)
    assert value is NotImplemented

    value = item is True
    assert value is False

    value = item == 100
    assert value is False


def test_range_part_raises_if_start_gt_end():
    with pytest.raises(ValueError):
        RangePart(400, 300)

    with pytest.raises(ValueError):
        part = RangePart(100, 300)
        part.start = 400

    with pytest.raises(ValueError):
        part = RangePart(100, 300)
        part.end = 50


def test_range_part_raises_if_any_part_is_negative():
    with pytest.raises(ValueError):
        RangePart(-100, 0)

    with pytest.raises(ValueError):
        part = RangePart(100, 300)
        part.start = -100

    with pytest.raises(ValueError):
        part = RangePart(100, 300)
        part.end = -50


def test_range_part_can_satisfy_raises_if_both_ends_are_none():
    part = RangePart(None, None)

    with pytest.raises(TypeError):
        part.can_satisfy(200)


def test_range_part_helper_methods():
    part_without_start = RangePart(None, 300)
    part_without_end = RangePart(500, None)

    assert part_without_start.is_suffix_length is True
    assert part_without_start.is_to_end is False

    assert part_without_end.is_to_end is True
    assert part_without_end.is_suffix_length is False

    assert repr(part_without_end) == "500-"
    assert repr(part_without_start) == "-300"


def test_range_throws_value_error_for_invalid_value():
    with pytest.raises(ValueError):
        Range.parse("bytes=100-200, 400-600, 300-500=50-150")
