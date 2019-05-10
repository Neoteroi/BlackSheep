import pytest
from typing import List
from pytest import raises
from blacksheep import Request, Headers, Header, JsonContent
from blacksheep.server.bindings import FromJson, FromHeader, InvalidRequestBody, MissingConverterError


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
@pytest.mark.parametrize('expected_type,header_value,expected_value', [
    [str, b'Foo', 'Foo'],
    [str, b'Hello%20World%21%3F', 'Hello World!?'],
    [int, b'1', 1],
    [int, b'10', 10],
    [float, b'1.5', 1.5],
    [float, b'1241.5', 1241.5],
])
async def test_from_header_binding(expected_type, header_value, expected_value):

    request = Request(b'GET', b'/', Headers([
        Header(b'X-Foo', header_value)
    ]), None)

    parameter = FromHeader('X-Foo', expected_type)

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value == expected_value


@pytest.mark.asyncio
async def test_from_header_raises_for_missing_default_converter():

    with raises(MissingConverterError, message="Cannot determine a default converter for type "
                                               "`<class 'tests.test_bindings.ExampleOne'>`. "
                                               "Please define a converter method for this binder (FromHeader)."):
        FromHeader('X-Foo', ExampleOne)
