import pytest
from blacksheep.ranges import Range, RangePart, InvalidRangeValue


@pytest.mark.parametrize('range_a,range_b,equals', [
    [
        Range('bytes', [RangePart(100, None)]),
        Range('bytes', [RangePart(100, None)]),
        True
    ],
    [
        Range('bytes', [RangePart(100, None)]),
        Range('bytes', [RangePart(None, 100)]),
        False
    ],
    [
        Range('bytes', [RangePart(100, 200), RangePart(400, 600)]),
        Range('bytes', [RangePart(100, 200), RangePart(400, 600)]),
        True
    ],
    [
        Range('bytes', [RangePart(100, 200), RangePart(400, 600)]),
        Range('bytes', [RangePart(100, 200), RangePart(400, 650)]),
        False
    ],
    [
        Range('bytes', [RangePart(100, 200), RangePart(400, 600), RangePart(300, 500)]),
        Range('bytes', [RangePart(100, 200), RangePart(400, 600), RangePart(300, 500)]),
        True
    ],
])
def test_range_equality(range_a, range_b, equals):
    assert (range_a == range_b) is equals


@pytest.mark.parametrize('value,expected_range', [
    (b'bytes=100-', Range('bytes', [RangePart(100, None)])),
    (b'bytes=-120', Range('bytes', [RangePart(None, 120)])),
    ('bytes=-120', Range('bytes', [RangePart(None, 120)])),
    ('bytes=100-200, 400-600, 300-500', Range('bytes', [RangePart(100, 200),
                                                        RangePart(400, 600),
                                                        RangePart(300, 500)])),
    ('bytes=100-200,400-600,300-500', Range('bytes', [RangePart(100, 200),
                                                      RangePart(400, 600),
                                                      RangePart(300, 500)]))
])
def test_parse_range(value, expected_range):
    parsed_range = Range.parse(value)
    assert parsed_range == expected_range


@pytest.mark.parametrize('invalid_value', [
    '1000',
    '100-200',
    'bytes=10',
    'bytes=100--200',
    'bytes=100AA, 400-600, 300-500',
    'bytes=100-200, 400-600, 300-A0',
    'bytes=100-AA, 400-600, 300-500'
])
def test_raise_for_invalid_value(invalid_value):
    with pytest.raises(InvalidRangeValue):
        Range.parse(invalid_value)
