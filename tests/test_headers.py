import pytest
from blacksheep import HttpHeader, HttpHeaderCollection
from blacksheep import scribe


@pytest.mark.parametrize('values', [
    {
        b'AAA': b'BBB'
    },
    {
        b'AAA': b'BBB',
        b'CCC': b'DDD',
        b'EEE': b'FFF',
    },
    {
        b'Content-Length': b'61',
        b'Content-Type': b'application/json; charset=utf-8',
        b'Server': b'Python/3.7',
        b'Date': b'Fri, 02 Nov 2018 12:32:07 GMT',
    },
])
def test_http_header_collection_instantiating_with_dict_values(values):
    headers = HttpHeaderCollection(values)

    for key, value in values.items():
        header = headers[key]
        assert len(header) == 1
        assert header[0].name == key
        assert header[0].value == value


@pytest.mark.parametrize('values', [
    [
        HttpHeader(b'AAA', b'BBB')
    ],
    [
        HttpHeader(b'AAA', b'BBB'),
        HttpHeader(b'CCC', b'DDD'),
        HttpHeader(b'EEE', b'FFF')
    ],
    [
        HttpHeader(b'Content-Length', b'61'),
        HttpHeader(b'Content-Type', b'application/json; charset=utf-8'),
        HttpHeader(b'Server', b'Python/3.7'),
        HttpHeader(b'Date', b'Fri, 02 Nov 2018 12:32:07 GMT')
    ],
])
def test_http_header_collection_instantiating_with_list_of_headers(values):
    headers = HttpHeaderCollection(values)

    for input_header in values:
        header = headers[input_header.name]
        assert len(header) == 1
        assert header[0].name == input_header.name
        assert header[0].value == input_header.value
        assert header[0] is input_header


@pytest.mark.parametrize('values', [
    [
        HttpHeader(b'Content-Length', b'61'),
        HttpHeader(b'Content-Type', b'application/json; charset=utf-8'),
        HttpHeader(b'Server', b'Python/3.7'),
        HttpHeader(b'Date', b'Fri, 02 Nov 2018 12:32:07 GMT'),
        HttpHeader(b'Set-Cookie', b'foo=foo;'),
        HttpHeader(b'Set-Cookie', b'ufo=ufo;'),
        HttpHeader(b'Set-Cookie', b'uof=uof;')
    ],
])
def test_http_header_collection_instantiating_with_list_of_headers_repeated_values(values):
    headers = HttpHeaderCollection(values)

    for input_header in values:
        input_headers_with_same_name = [x for x in values if x.name == input_header.name]

        header = headers[input_header.name]
        assert len(header) == len(input_headers_with_same_name)
        assert any(x == y for x in header for y in input_headers_with_same_name)


def test_http_header_collection_item_setter():
    headers = HttpHeaderCollection()

    example = headers.get(b'example')
    assert example == []

    headers[b'example'] = b'Hello, World'

    example = headers.get(b'example')
    assert len(example) == 1

    header = example[0]
    assert header.name == b'example'
    assert header.value == b'Hello, World'


def test_http_header_collection_item_get_single_case_insensitive():
    headers = HttpHeaderCollection()
    headers[b'example'] = b'Hello, World'

    header = headers.get_single(b'Example')
    assert header is not None
    assert header.name == b'example'
    assert header.value == b'Hello, World'


def test_http_header_collection_item_getter_case_insensitive():
    headers = HttpHeaderCollection()
    headers[b'example'] = b'Hello, World'

    example = headers[b'Example']
    assert len(example) == 1

    header = example[0]
    assert header.name == b'example'
    assert header.value == b'Hello, World'


@pytest.mark.parametrize('name_a,value_a,name_b,value_b,expected_result', [
    [b'Hello', b'World', b'Hello', b'World', True],
    [b'hello', b'World', b'Hello', b'World', True],
    [b'Hello', b'World', b'Hello', b'Kitty', False]
])
def test_http_header_check_equality(name_a, value_a, name_b, value_b, expected_result):
    a = HttpHeader(name_a, value_a)
    b = HttpHeader(name_b, value_b)

    assert (a == b) == expected_result
    assert (a != b) != expected_result
    assert (b != a) != expected_result


def test_http_header_collection_add_many_items():
    headers = HttpHeaderCollection()

    values = {
        b'A': b'B',
        b'C': b'D',
        b'E': b'F',
    }

    headers.add_many(values)

    for key, value in values.items():
        header = headers.get_single(key)
        assert header is not None
        assert header.name == key
        assert header.value == value


def test_http_header_collection_add_multiple_times_items():
    headers = HttpHeaderCollection()

    values = [
        HttpHeader(b'Cookie', b'Hello=World;'),
        HttpHeader(b'Cookie', b'Foo=foo;'),
        HttpHeader(b'Cookie', b'Ufo=ufo;'),
    ]

    headers.add_many(values)

    cookie_headers = headers[b'cookie']

    assert cookie_headers
    assert len(cookie_headers) == 3
    assert any(x.value == b'Hello=World;' for x in cookie_headers)
    assert any(x.value == b'Foo=foo;' for x in cookie_headers)
    assert any(x.value == b'Ufo=ufo;' for x in cookie_headers)


def test_http_header_collection_get_single_raises_if_more_items_are_present():
    headers = HttpHeaderCollection()

    values = [
        HttpHeader(b'Cookie', b'Hello=World;'),
        HttpHeader(b'Cookie', b'Foo=foo;'),
        HttpHeader(b'Cookie', b'Ufo=ufo;'),
    ]

    headers.add_many(values)
    # keeps only the last one, if a single header is expected
    headers.get_single(b'cookie').value == b'Ufo=ufo;'


def test_http_header_collection_concatenation_with_list_of_headers():
    headers = HttpHeaderCollection([
        HttpHeader(b'Hello', b'World'),
        HttpHeader(b'Svil', b'Power'),
    ])

    with_addition = headers + [HttpHeader(b'Foo', b'foo'), HttpHeader(b'Ufo', b'ufo')]

    for name in {b'foo', b'ufo'}:
        assert headers[name] == []

        example = with_addition[name]
        assert len(example) == 1

        header = example[0]
        assert header.name.lower() == name
        assert header.value == name


def test_http_header_collection_concatenation_with_other_collection():
    headers = HttpHeaderCollection([
        HttpHeader(b'Hello', b'World'),
        HttpHeader(b'Svil', b'Power'),
    ])

    with_addition = headers + HttpHeaderCollection([HttpHeader(b'Foo', b'foo'), HttpHeader(b'Ufo', b'ufo')])

    for name in {b'foo', b'ufo'}:
        assert headers[name] == []

        example = with_addition[name]
        assert len(example) == 1

        header = example[0]
        assert header.name.lower() == name
        assert header.value == name


def test_iadd_http_header_collection_concatenation_with_header():
    headers = HttpHeaderCollection([
        HttpHeader(b'Hello', b'World'),
        HttpHeader(b'Svil', b'Power'),
    ])

    headers += HttpHeader(b'Foo', b'foo')

    example = headers[b'Foo']
    assert len(example) == 1

    header = example[0]
    assert header.name == b'Foo'
    assert header.value == b'foo'


def test_iadd_http_header_collection_concatenation_with_list_of_headers():
    headers = HttpHeaderCollection([
        HttpHeader(b'Hello', b'World'),
        HttpHeader(b'Svil', b'Power'),
    ])

    headers += [HttpHeader(b'foo', b'foo'),
                HttpHeader(b'ufo', b'ufo')]

    for name in {b'foo', b'ufo'}:
        example = headers[name]
        assert len(example) == 1

        header = example[0]
        assert header.name.lower() == name
        assert header.value == name


def test_iadd_http_header_collection_concatenation_with_collection_of_headers():
    headers = HttpHeaderCollection([
        HttpHeader(b'Hello', b'World'),
        HttpHeader(b'Svil', b'Power'),
    ])

    headers += HttpHeaderCollection(
                [HttpHeader(b'foo', b'foo'),
                HttpHeader(b'ufo', b'ufo')])

    for name in {b'foo', b'ufo'}:
        example = headers[name]
        assert len(example) == 1

        header = example[0]
        assert header.name.lower() == name
        assert header.value == name


def test_iadd_http_header_collection_concatenation_with_duplicate_header():
    headers = HttpHeaderCollection([
        HttpHeader(b'Hello', b'World'),
        HttpHeader(b'Svil', b'Power'),
    ])

    headers += HttpHeader(b'Svil', b'Kitty')
    example = headers[b'Svil']

    assert len(example) == 2
    assert any(x.value == b'Power' for x in example)
    assert any(x.value == b'Kitty' for x in example)


