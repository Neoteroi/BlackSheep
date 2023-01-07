import pytest

from blacksheep import Header, Headers


@pytest.mark.parametrize(
    "values",
    [
        [(b"AAA", b"BBB")],
        [(b"AAA", b"BBB"), (b"CCC", b"DDD"), (b"EEE", b"FFF")],
        [
            (b"Content-Length", b"61"),
            (b"Content-Type", b"application/json; charset=utf-8"),
            (b"Server", b"Python/3.7"),
            (b"Date", b"Fri, 02 Nov 2018 12:32:07 GMT"),
        ],
    ],
)
def test_http_header_collection_instantiating_with_list_of_tuples(values):
    headers = Headers(values)

    for input_header in values:
        header = headers[input_header[0]]
        assert len(header) == 1
        assert header[0] == input_header[1]


@pytest.mark.parametrize(
    "values",
    [
        [
            (b"Content-Length", b"61"),
            (b"Content-Type", b"application/json; charset=utf-8"),
            (b"Server", b"Python/3.7"),
            (b"Date", b"Fri, 02 Nov 2018 12:32:07 GMT"),
            (b"Set-Cookie", b"foo=foo;"),
            (b"Set-Cookie", b"ufo=ufo;"),
            (b"Set-Cookie", b"uof=uof;"),
        ],
    ],
)
def test_http_header_collection_instantiating_with_list_of_headers_repeated_values(
    values,
):
    headers = Headers(values)

    for input_header in values:
        input_headers_with_same_name = [x[1] for x in values if x[0] == input_header[0]]

        header = headers[input_header[0]]
        assert len(header) == len(input_headers_with_same_name)
        assert any(x == y for x in header for y in input_headers_with_same_name)


def test_http_header_collection_item_setter():
    headers = Headers()

    example = headers.get(b"example")
    assert example == tuple()

    headers[b"example"] = b"Hello, World"

    example = headers.get(b"example")

    assert example == (b"Hello, World",)


def test_http_header_collection_item_get_single_case_insensitive():
    headers = Headers()
    headers[b"example"] = b"Hello, World"

    header = headers.get_single(b"Example")
    assert header == b"Hello, World"


def test_http_header_collection_item_getter_case_insensitive():
    headers = Headers()
    headers[b"example"] = b"Hello, World"

    header = headers[b"Example"]
    assert header == (b"Hello, World",)


@pytest.mark.parametrize(
    "name_a,value_a,name_b,value_b,expected_result",
    [
        [b"Hello", b"World", b"Hello", b"World", True],
        [b"hello", b"World", b"Hello", b"World", True],
        [b"Hello", b"World", b"Hello", b"Kitty", False],
    ],
)
def test_http_header_check_equality(name_a, value_a, name_b, value_b, expected_result):
    a = Header(name_a, value_a)
    b = Header(name_b, value_b)

    assert (a == b) == expected_result
    assert (a != b) != expected_result
    assert (b != a) != expected_result


def test_http_header_collection_add_many_items():
    headers = Headers()

    values = {
        b"A": b"B",
        b"C": b"D",
        b"E": b"F",
    }

    headers.add_many(values)

    for key, value in values.items():
        header = headers.get_single(key)
        assert header is not None
        assert header == value


def test_http_header_collection_add_multiple_times_items():
    headers = Headers()

    values = [
        (b"Cookie", b"Hello=World;"),
        (b"Cookie", b"Foo=foo;"),
        (b"Cookie", b"Ufo=ufo;"),
    ]

    headers.add_many(values)

    cookie_headers = headers[b"cookie"]

    assert cookie_headers
    assert len(cookie_headers) == 3
    assert any(x == b"Hello=World;" for x in cookie_headers)
    assert any(x == b"Foo=foo;" for x in cookie_headers)
    assert any(x == b"Ufo=ufo;" for x in cookie_headers)


def test_http_header_collection_get_single_raises_if_more_items_are_present():
    headers = Headers()

    values = [
        (b"Cookie", b"Hello=World;"),
        (b"Cookie", b"Foo=foo;"),
        (b"Cookie", b"Ufo=ufo;"),
    ]

    headers.add_many(values)

    with pytest.raises(ValueError):
        headers.get_single(b"cookie")


def test_http_header_collection_concatenation_with_list_of_headers():
    headers = Headers([(b"Hello", b"World"), (b"Svil", b"Power")])

    with_addition = headers + [(b"Foo", b"foo"), (b"Ufo", b"ufo")]

    for name in {b"foo", b"ufo"}:
        assert headers[name] == tuple()

        example = with_addition[name]
        assert len(example) == 1

        header = example[0]
        assert header == name


def test_http_header_collection_concatenation_with_other_collection():
    headers = Headers([(b"Hello", b"World"), (b"Svil", b"Power")])

    with_addition = headers + Headers([(b"Foo", b"foo"), (b"Ufo", b"ufo")])

    for name in {b"foo", b"ufo"}:
        assert headers[name] == tuple()

        example = with_addition[name]
        assert len(example) == 1

        header = example[0]
        assert header == name


def test_iadd_http_header_collection_concatenation_with_():
    headers = Headers([(b"Hello", b"World"), (b"Svil", b"Power")])

    headers += (b"Foo", b"foo")

    example = headers[b"Foo"]
    assert len(example) == 1

    header = example[0]
    assert header == b"foo"


def test_iadd_http_header_collection_concatenation_with_list_of_headers():
    headers = Headers([(b"Hello", b"World"), (b"Svil", b"Power")])

    headers += [(b"foo", b"foo"), (b"ufo", b"ufo")]

    for name in {b"foo", b"ufo"}:
        example = headers[name]
        assert len(example) == 1

        header = example[0]
        assert header == name


def test_iadd_http_header_collection_concatenation_with_collection_of_headers():
    headers = Headers([(b"Hello", b"World"), (b"Svil", b"Power")])

    headers += Headers([(b"foo", b"foo"), (b"ufo", b"ufo")])

    for name in {b"foo", b"ufo"}:
        example = headers[name]
        assert len(example) == 1

        header = example[0]
        assert header == name


def test_iadd_http_header_collection_concatenation_with_duplicate_():
    headers = Headers([(b"Hello", b"World"), (b"Svil", b"Power")])

    headers += (b"Svil", b"Kitty")
    example = headers[b"Svil"]

    assert len(example) == 2
    assert any(x == b"Power" for x in example)
    assert any(x == b"Kitty" for x in example)


def test_case_insensitive_contains():
    headers = Headers([(b"Hello", b"World")])

    assert b"hello" in headers
    assert b"hElLo" in headers
    assert b"HELLO" in headers
