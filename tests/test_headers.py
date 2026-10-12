import pytest

from blacksheep import Header, Headers, Request, Response
from blacksheep.scribe import send_asgi_response


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


@pytest.mark.parametrize("name", ["X-Example", b"X-Example"])
@pytest.mark.parametrize("value", ["caf\xe9", b"caf\xe9", "", b""])
def test_text_assignment_stores_bytes_and_replaces_all_matching_entries(name, value):
    headers = Headers(
        [(b"x-example", b"old"), (b"X-EXAMPLE", b"other"), (b"Other", b"kept")]
    )
    headers[name] = value

    raw_value = value.encode("latin-1") if isinstance(value, str) else value
    assert headers.values == [(b"Other", b"kept"), (b"X-Example", raw_value)]
    assert headers[b"x-example"] == (raw_value,)
    assert headers.get_text_values("X-EXAMPLE") == (raw_value.decode("latin-1"),)


def test_update_accepts_text_and_bytes():
    headers = Headers()
    headers.update({"X-Text": "value", b"X-Bytes": b"raw", "X-Mixed": b"mixed"})

    assert list(headers.items()) == [
        (b"X-Text", b"value"),
        (b"X-Bytes", b"raw"),
        (b"X-Mixed", b"mixed"),
    ]


@pytest.mark.parametrize("name", ["SET-cookie", b"SET-cookie"])
def test_get_text_values_preserves_multiple_values_and_raw_storage(name):
    values = [(b"Set-Cookie", b"a=1"), (b"set-cookie", b"b=\xff")]
    headers = Headers(values)

    assert headers.get_text_values(name) == ("a=1", "b=\xff")
    assert headers.get_text_values("missing") == ()
    assert headers.values is values
    assert headers[b"set-cookie"] == (b"a=1", b"b=\xff")


@pytest.mark.parametrize(
    "method", ["get_text_values", "get_first_text", "get_single_text"]
)
def test_text_reads_support_explicit_encoding_and_strict_decoding(method):
    headers = Headers([(b"X-Text", "caf\xe9".encode("utf-8"))])
    read = getattr(headers, method)
    expected = ("caf\xe9",) if method == "get_text_values" else "caf\xe9"
    assert read("X-Text", encoding="utf-8") == expected

    headers[b"X-Text"] = b"\xff"
    with pytest.raises(UnicodeDecodeError):
        read("X-Text", encoding="utf-8")


@pytest.mark.parametrize("name", ["X-EXAMPLE", b"X-EXAMPLE"])
@pytest.mark.parametrize("value", [b"", b"caf\xe9"])
def test_single_value_text_reads(name, value):
    headers = Headers([(b"x-example", value)])
    assert headers.get_first_text(name) == value.decode("latin-1")
    assert headers.get_single_text(name) == value.decode("latin-1")
    assert headers.get_first_text("missing") is None
    with pytest.raises(ValueError, match="does not contain one header"):
        headers.get_single_text("missing")


def test_first_text_only_decodes_first_value_and_single_text_rejects_duplicates():
    headers = Headers([(b"X-Example", b"first"), (b"x-example", b"\xff")])
    assert headers.get_first_text("X-Example", encoding="utf-8") == "first"
    with pytest.raises(ValueError, match="more than one header"):
        headers.get_single_text("X-Example", encoding="utf-8")


@pytest.mark.parametrize(
    "name,value",
    [("X-\xe9", "value"), ("X-Example", "\u20ac")],
)
def test_text_assignment_encoding_errors_do_not_mutate_headers(name, value):
    headers = Headers([(b"X-Example", b"original")])
    with pytest.raises(UnicodeEncodeError):
        headers[name] = value
    assert headers.values == [(b"X-Example", b"original")]


@pytest.mark.parametrize(
    "method", ["get_text_values", "get_first_text", "get_single_text"]
)
def test_text_reads_reject_non_ascii_names(method):
    with pytest.raises(UnicodeEncodeError):
        getattr(Headers(), method)("X-\xe9")


@pytest.mark.parametrize(
    "name,value",
    [(123, "value"), ("X-Example", 123), (None, "value"), ("X-Example", None)],
)
def test_assignment_rejects_invalid_types_without_mutating_headers(name, value):
    headers = Headers([(b"X-Example", b"original")])
    with pytest.raises(TypeError):
        headers[name] = value
    assert headers.values == [(b"X-Example", b"original")]


@pytest.mark.parametrize("name", [123, None])
@pytest.mark.parametrize(
    "method", ["get_text_values", "get_first_text", "get_single_text"]
)
def test_text_reads_reject_invalid_name_type(name, method):
    with pytest.raises(TypeError):
        getattr(Headers(), method)(name)


def test_request_text_headers_share_raw_storage():
    request = Request("GET", b"/", [(b"X-Example", b"original")])
    assert request.headers.get_text_values("x-example") == ("original",)
    request.headers["X-Example"] = "updated"
    assert request.get_first_header(b"x-example") == b"updated"


async def test_response_text_headers_are_sent_as_bytes():
    response = Response(200)
    response.headers["X-Example"] = "caf\xe9"
    response.headers.update({"X-Other": "value"})
    messages = []

    async def send(message):
        messages.append(message)

    await send_asgi_response(response, send)

    assert messages[0]["type"] == "http.response.start"
    assert (b"X-Example", b"caf\xe9") in messages[0]["headers"]
    assert (b"X-Other", b"value") in messages[0]["headers"]
    assert all(
        isinstance(name, bytes) and isinstance(value, bytes)
        for name, value in messages[0]["headers"]
    )


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
