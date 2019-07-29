import pytest
from pytest import raises
from typing import List, Sequence, Set, Tuple
from blacksheep import Request, Headers, Header, JsonContent
from blacksheep.server.bindings import (FromJson,
                                        FromHeader,
                                        FromQuery,
                                        FromRoute,
                                        FromServices,
                                        RequestBinder,
                                        InvalidRequestBody,
                                        MissingConverterError,
                                        BadRequest)


JsonContentType = Header(b'Content-Type', b'application/json')


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

    request = Request('POST', b'/', Headers([
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

    request = Request('POST', b'/', Headers([
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

    request = Request('POST', b'/', Headers([
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

    request = Request('POST', b'/', Headers(), JsonContent({
        'a': 'world',
        'b': 9000
    }))

    parameter = FromJson(ExampleOne)

    value = await parameter.get_value(request)

    assert value is None


@pytest.mark.asyncio
async def test_from_body_json_binding_invalid_input():

    request = Request('POST', b'/', Headers([
        JsonContentType
    ]), JsonContent({
        'c': 1,
        'd': 2
    }))

    parameter = FromJson(ExampleOne)

    with raises(InvalidRequestBody):
        await parameter.get_value(request)


@pytest.mark.asyncio
@pytest.mark.parametrize('expected_type,header_value,expected_value', [
    [str, b'Foo', 'Foo'],
    [str, b'foo', 'foo'],
    [str, b'\xc5\x81ukasz', 'Łukasz'],
    [str, b'Hello%20World%21%3F', 'Hello World!?'],
    [int, b'1', 1],
    [int, b'10', 10],
    [float, b'1.5', 1.5],
    [float, b'1241.5', 1241.5],
    [bool, b'1', True],
    [bool, b'0', False]
])
async def test_from_header_binding(expected_type, header_value, expected_value):

    request = Request('GET', b'/', Headers([
        Header(b'X-Foo', header_value)
    ]), None)

    parameter = FromHeader(expected_type, 'X-Foo')

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value == expected_value


@pytest.mark.asyncio
@pytest.mark.parametrize('expected_type,query_value,expected_value', [
    [str, b'Foo', 'Foo'],
    [str, b'foo', 'foo'],
    [str, b'Hello%20World%21%3F', 'Hello World!?'],
    [int, b'1', 1],
    [int, b'10', 10],
    [float, b'1.5', 1.5],
    [float, b'1241.5', 1241.5],
    [bool, b'1', True],
    [bool, b'0', False]
])
async def test_from_query_binding(expected_type, query_value, expected_value):

    request = Request('GET', b'/?foo=' + query_value, Headers(), None)

    parameter = FromQuery(expected_type, 'foo')

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value == expected_value


@pytest.mark.asyncio
@pytest.mark.parametrize('expected_type,route_value,expected_value', [
    [str, 'Foo', 'Foo'],
    [str, 'foo', 'foo'],
    [str, 'Hello%20World%21%3F', 'Hello World!?'],
    [int, '1', 1],
    [int, '10', 10],
    [float, '1.5', 1.5],
    [float, '1241.5', 1241.5],
    [bool, '1', True],
    [bool, '0', False]
])
async def test_from_route_binding(expected_type, route_value, expected_value):

    request = Request('GET', b'/', Headers(), None)
    request.route_values = {
        'name': route_value
    }

    parameter = FromRoute(expected_type, 'name')

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value == expected_value


@pytest.mark.asyncio
@pytest.mark.parametrize('binder_type', [
    FromHeader,
    FromQuery,
    FromRoute
])
async def test_raises_for_missing_default_converter(binder_type):

    with raises(MissingConverterError):
        binder_type('example', ExampleOne)


@pytest.mark.asyncio
@pytest.mark.parametrize('expected_type,invalid_value', [
    [int, 'x'],
    [int, ''],
    [float, 'x'],
    [float, ''],
    [bool, 'x'],
    [bool, 'yes']
])
async def test_from_route_raises_for_invalid_parameter(expected_type, invalid_value):

    request = Request('GET', b'/', Headers(), None)
    request.route_values = {
        'name': invalid_value
    }

    parameter = FromRoute(expected_type, 'name')

    with raises(BadRequest):
        await parameter.get_value(request)


@pytest.mark.asyncio
@pytest.mark.parametrize('expected_type,invalid_value', [
    [int, b'x'],
    [int, b''],
    [float, b'x'],
    [float, b''],
    [bool, b'x'],
    [bool, b'yes']
])
async def test_from_query_raises_for_invalid_parameter(expected_type, invalid_value: bytes):
    request = Request('GET', b'/?foo=' + invalid_value, Headers(), None)

    parameter = FromQuery(expected_type, 'foo', required=True)

    with raises(BadRequest):
        await parameter.get_value(request)


@pytest.mark.asyncio
async def test_from_services():
    request = Request('GET', b'/', Headers(), None)

    service_instance = ExampleOne(1, 2)
    services = {
        ExampleOne: service_instance
    }

    parameter = FromServices(ExampleOne, services)
    value = await parameter.get_value(request)

    assert value is service_instance


@pytest.mark.asyncio
@pytest.mark.parametrize('declared_type,expected_type,header_values,expected_values', [
    [List[str], list, [b'Lorem', b'ipsum', b'dolor'], ['Lorem', 'ipsum', 'dolor']],
    [Tuple[str], tuple, [b'Lorem', b'ipsum', b'dolor'], ('Lorem', 'ipsum', 'dolor')],
    [Set[str], set, [b'Lorem', b'ipsum', b'dolor'], {'Lorem', 'ipsum', 'dolor'}],
    [Sequence[str], list, [b'Lorem', b'ipsum', b'dolor'], ['Lorem', 'ipsum', 'dolor']],
])
async def test_from_header_binding_iterables(declared_type, expected_type, header_values, expected_values):

    request = Request('GET', b'/', Headers([
        Header(b'X-Foo', value) for value in header_values
    ]), None)

    parameter = FromHeader(declared_type, 'X-Foo')

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value == expected_values


@pytest.mark.asyncio
@pytest.mark.parametrize('declared_type,expected_type,query_values,expected_values', [
    [list, list, [b'Lorem', b'ipsum', b'dolor'], ['Lorem', 'ipsum', 'dolor']],
    [tuple, tuple, [b'Lorem', b'ipsum', b'dolor'], ('Lorem', 'ipsum', 'dolor')],
    [set, set, [b'Lorem', b'ipsum', b'dolor'], {'Lorem', 'ipsum', 'dolor'}],
    [List, list, [b'Lorem', b'ipsum', b'dolor'], ['Lorem', 'ipsum', 'dolor']],
    [Tuple, tuple, [b'Lorem', b'ipsum', b'dolor'], ('Lorem', 'ipsum', 'dolor')],
    [Set, set, [b'Lorem', b'ipsum', b'dolor'], {'Lorem', 'ipsum', 'dolor'}],
    [List[str], list, [b'Lorem', b'ipsum', b'dolor'], ['Lorem', 'ipsum', 'dolor']],
    [Tuple[str], tuple, [b'Lorem', b'ipsum', b'dolor'], ('Lorem', 'ipsum', 'dolor')],
    [Set[str], set, [b'Lorem', b'ipsum', b'dolor'], {'Lorem', 'ipsum', 'dolor'}],
    [Sequence[str], list, [b'Lorem', b'ipsum', b'dolor'], ['Lorem', 'ipsum', 'dolor']],
    [List[int], list, [b'10'], [10]],
    [List[int], list, [b'0', b'1', b'0'], [0, 1, 0]],
    [List[int], list, [b'0', b'1', b'0', b'2'], [0, 1, 0, 2]],
    [List[bool], list, [b'1'], [True]],
    [List[bool], list, [b'0', b'1', b'0'], [False, True, False]],
    [List[bool], list, [b'0', b'1', b'0', b'true'], [False, True, False, True]],
    [List[float], list, [b'10.2'], [10.2]],
    [List[float], list, [b'0.3', b'1', b'0'], [0.3, 1.0, 0]],
    [List[float], list, [b'0.5', b'1', b'0', b'2'], [0.5, 1.0, 0, 2.0]],
    [Tuple[float], tuple, [b'10.2'], (10.2,)],
    [Tuple[float], tuple, [b'0.3', b'1', b'0'], (0.3, 1.0, 0)],
    [Tuple[float], tuple, [b'0.5', b'1', b'0', b'2'], (0.5, 1.0, 0, 2.0)],
    [Set[int], set, [b'10'], {10}],
    [Set[int], set, [b'0', b'1', b'0'], {0, 1, 0}],
    [Set[int], set, [b'0', b'1', b'0', b'2'], {0, 1, 0, 2}],
])
async def test_from_query_binding_iterables(declared_type, expected_type, query_values, expected_values):
    qs = b'&foo='.join([value for value in query_values])

    request = Request('GET', b'/?foo=' + qs, Headers(), None)

    parameter = FromQuery(declared_type, 'foo')

    values = await parameter.get_value(request)

    assert isinstance(values, expected_type)
    assert values == expected_values


@pytest.mark.asyncio
@pytest.mark.parametrize('declared_type', [
    List[List[str]],
    Tuple[Tuple[str]],
    List[list],
])
async def test_nested_iterables_raise_missing_converter_from_header(declared_type):
    with raises(MissingConverterError):
        FromHeader(declared_type)


@pytest.mark.asyncio
@pytest.mark.parametrize('declared_type', [
    List[List[str]],
    Tuple[Tuple[str]],
    List[list],
])
async def test_nested_iterables_raise_missing_converter_from_query(declared_type):
    with raises(MissingConverterError):
        FromQuery('example', declared_type)


@pytest.mark.asyncio
async def test_request_binder():
    request = Request('GET', b'/', Headers(), None)

    parameter = RequestBinder()

    value = await parameter.get_value(request)

    assert value is request
