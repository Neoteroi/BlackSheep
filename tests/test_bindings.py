import pytest
from pytest import raises
from blacksheep import Request, Headers, Header, JsonContent
from blacksheep.server.bindings import FromJson, FromHeader, InvalidRequestBody


JsonContentType = Header(b'Content-Type', b'application/json')
XmlContentType = Header(b'Content-Type', b'application/xml')


class ExampleOne:

    def __init__(self, a, b):
        self.a = a
        self.b = b


class ExampleTwo:

    def __init__(self, a, b, **kwargs):
        self.a = a
        self.b = b


@pytest.mark.asyncio
async def test_from_body_json_binding():

    request = Request(b'POST', b'/', Headers([
        JsonContentType
    ]), JsonContent({
        'a': 'world',
        'b': 9000
    }))

    parameter = FromJson(ExampleOne)

    value = await parameter.get_value(request)

    assert isinstance(value, ExampleOne)
    assert value.a == 'world'
    assert value.b == 9000


@pytest.mark.asyncio
async def test_from_body_json_binding_extra_parameters_strategy():

    request = Request(b'POST', b'/', Headers([
        JsonContentType
    ]), JsonContent({
        'a': 'world',
        'b': 9000,
        'c': 'This is an extra parameter, accepted by constructor explicitly'
    }))

    parameter = FromJson(ExampleTwo)

    value = await parameter.get_value(request)

    assert isinstance(value, ExampleTwo)
    assert value.a == 'world'
    assert value.b == 9000


@pytest.mark.asyncio
async def test_from_body_json_with_converter():

    request = Request(b'POST', b'/', Headers([
        JsonContentType
    ]), JsonContent({
        'a': 'world',
        'b': 9000,
        'c': 'This is an extra parameter, accepted by constructor explicitly'
    }))

    def convert(data):
        return ExampleOne(data.get('a'), data.get('b'))

    parameter = FromJson(ExampleOne, converter=convert)

    value = await parameter.get_value(request)

    assert isinstance(value, ExampleOne)
    assert value.a == 'world'
    assert value.b == 9000


@pytest.mark.asyncio
async def test_from_body_json_binding_request_missing_content_type():

    request = Request(b'POST', b'/', Headers(), JsonContent({
        'a': 'world',
        'b': 9000
    }))

    parameter = FromJson(ExampleOne)

    value = await parameter.get_value(request)

    assert value is None


@pytest.mark.asyncio
async def test_from_body_json_binding_invalid_input():

    request = Request(b'POST', b'/', Headers([
        JsonContentType
    ]), JsonContent({
        'c': 1,
        'd': 2
    }))

    parameter = FromJson(ExampleOne)

    with raises(InvalidRequestBody, message="got an unexpected parameter 'c'"):
        await parameter.get_value(request)


@pytest.mark.asyncio
async def test_from_header_binding():
    request = Request(b'GET', b'/', Headers([
        Header(b'X-Foo', b'Foo')
    ]), None)

    parameter = FromHeader(b'X-Foo', str)

    value = await parameter.get_value(request)

    assert isinstance(value, str)
    assert value == 'Foo'
