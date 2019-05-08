import pytest
from blacksheep import Request, Headers, Header, JsonContent
from blacksheep.server.bindings import FromBody


JsonContentType = Header(b'Content-Type', b'application/json')
XmlContentType = Header(b'Content-Type', b'application/xml')


class ExampleOne:

    def __init__(self, a, b):
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

    parameter = FromBody(ExampleOne)

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

    parameter = FromBody(ExampleOne)

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

    parameter = FromBody(ExampleOne)

    value = await parameter.get_value(request)

    assert isinstance(value, ExampleOne)
    assert value.a == 'world'
    assert value.b == 9000
