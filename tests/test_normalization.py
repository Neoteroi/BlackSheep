import pytest
from pytest import raises
from typing import List, Sequence, Optional
from blacksheep import Request, Headers, Header
from blacksheep.server.routing import Route
from blacksheep.server.bindings import FromHeader, FromQuery, IdentityBinder
from blacksheep.server.normalization import (get_from_body_parameter,
                                             AmbiguousMethodSignatureError,
                                             RouteBinderMismatch,
                                             get_binders,
                                             MultipleFromBodyBinders,
                                             FromJson,
                                             FromQuery,
                                             FromRoute,
                                             FromServices,
                                             RequestBinder,
                                             ExactBinder,
                                             normalize_handler,
                                             normalize_middleware)


class Pet:
    def __init__(self, name):
        self.name = name


class Cat(Pet):
    ...


class Dog(Pet):
    ...


def valid_method_one(a: FromJson(Cat)):
    print(a)


def valid_method_two(a: FromJson(Cat), b: str):
    print(a, b)


def valid_method_three(b: str, a: FromJson(Cat)):
    print(b, a)


def valid_method_four(a: FromJson(Dog)):
    print(a)


def invalid_method_one(a: FromJson(Cat), b: FromJson(Cat)):
    print(a, b)


def invalid_method_two(a: FromJson(Cat), b: FromJson(Dog)):
    print(a, b)


def invalid_method_three(a: FromJson(Cat), b: FromJson(Dog), c: FromJson(Dog)):
    print(a, b, c)


@pytest.mark.parametrize('valid_method,expected_type', [
    [valid_method_one, Cat],
    [valid_method_two, Cat],
    [valid_method_three, Cat],
    [valid_method_four, Dog]
])
def test_get_body_parameter_valid_method(valid_method, expected_type):
    from_body_param = get_from_body_parameter(valid_method)

    assert from_body_param.expected_type is expected_type


@pytest.mark.parametrize('invalid_method', [
    invalid_method_one,
    invalid_method_two,
    invalid_method_three
])
def test_get_body_parameter_invalid_method(invalid_method):

    with raises(MultipleFromBodyBinders):
        get_from_body_parameter(invalid_method)


def test_parameters_get_binders_default_query():

    def handler(a, b, c):
        ...

    binders = get_binders(Route(b'/', handler), {})

    assert all(isinstance(binder, FromQuery) for binder in binders)
    assert binders[0].name == 'a'
    assert binders[1].name == 'b'
    assert binders[2].name == 'c'


def test_identity_binder_by_param_name_user():

    async def handler(user):
        ...

    binders = get_binders(Route(b'/', handler), {})

    assert isinstance(binders[0], IdentityBinder)


def test_identity_binder_by_param_name_identity():
    async def handler(identity):
        ...

    binders = get_binders(Route(b'/', handler), {})

    assert isinstance(binders[0], IdentityBinder)


def test_parameters_get_binders_from_route():

    def handler(a, b, c):
        ...

    binders = get_binders(Route(b'/:a/:b/:c', handler), {})

    assert all(isinstance(binder, FromRoute) for binder in binders)
    assert binders[0].name == 'a'
    assert binders[1].name == 'b'
    assert binders[2].name == 'c'


def test_parameters_get_binders_from_services_by_name():

    def handler(a, b, c):
        ...

    binders = get_binders(Route(b'/', handler), {
        'a': object(),
        'b': object(),
        'c': object()
    })

    assert all(isinstance(binder, FromServices) for binder in binders)
    assert binders[0].expected_type == 'a'
    assert binders[1].expected_type == 'b'
    assert binders[2].expected_type == 'c'


def test_parameters_get_binders_from_services_by_type():

    def handler(a: str, b: int, c: Cat):
        ...

    binders = get_binders(Route(b'/', handler), {
        str: object(),
        int: object(),
        Cat: object()
    })

    assert all(isinstance(binder, FromServices) for binder in binders)
    assert binders[0].expected_type is str
    assert binders[1].expected_type is int
    assert binders[2].expected_type is Cat


def test_parameters_get_binders_from_body():

    def handler(a: Cat):
        ...

    binders = get_binders(Route(b'/', handler), {})
    assert len(binders) == 1
    binder = binders[0]

    assert isinstance(binder, FromJson)
    assert binder.expected_type is Cat
    assert binder.required is True


def test_parameters_get_binders_from_body_optional():

    def handler(a: Optional[Cat]):
        ...

    binders = get_binders(Route(b'/', handler), {})
    assert len(binders) == 1
    binder = binders[0]

    assert isinstance(binder, FromJson)
    assert binder.expected_type is Cat
    assert binder.required is False


def test_parameters_get_binders_simple_types_default_from_query():

    def handler(a: str, b: int, c: bool):
        ...

    binders = get_binders(Route(b'/', handler), {})

    assert all(isinstance(binder, FromQuery) for binder in binders)
    assert binders[0].name == 'a'
    assert binders[0].expected_type == str
    assert binders[1].name == 'b'
    assert binders[1].expected_type == int
    assert binders[2].name == 'c'
    assert binders[2].expected_type == bool


def test_parameters_get_binders_list_types_default_from_query():

    def handler(a: List[str], b: List[int], c: List[bool]):
        ...

    binders = get_binders(Route(b'/', handler), {})

    assert all(isinstance(binder, FromQuery) for binder in binders)
    assert binders[0].name == 'a'
    assert binders[0].expected_type == List[str]
    assert binders[1].name == 'b'
    assert binders[1].expected_type == List[int]
    assert binders[2].name == 'c'
    assert binders[2].expected_type == List[bool]


def test_parameters_get_binders_list_types_default_from_query_optional():

    def handler(a: Optional[List[str]]):
        ...

    binders = get_binders(Route(b'/', handler), {})

    assert all(isinstance(binder, FromQuery) for binder in binders)
    assert all(binder.required is False for binder in binders)
    assert binders[0].name == 'a'
    assert binders[0].expected_type == List[str]


def test_parameters_get_binders_list_types_default_from_query_required():

    def handler(a: List[str]):
        ...

    binders = get_binders(Route(b'/', handler), {})

    assert all(isinstance(binder, FromQuery) for binder in binders)
    assert all(binder.required for binder in binders)


def test_parameters_get_binders_sequence_types_default_from_query():

    def handler(a: Sequence[str], b: Sequence[int], c: Sequence[bool]):
        ...

    binders = get_binders(Route(b'/', handler), {})

    assert all(isinstance(binder, FromQuery) for binder in binders)
    assert binders[0].name == 'a'
    assert binders[0].expected_type == Sequence[str]
    assert binders[1].name == 'b'
    assert binders[1].expected_type == Sequence[int]
    assert binders[2].name == 'c'
    assert binders[2].expected_type == Sequence[bool]


def test_throw_for_ambiguous_binder_multiple_from_body():

    def handler(a: Cat, b: Dog):
        ...

    with pytest.raises(AmbiguousMethodSignatureError):
        get_binders(Route(b'/', handler), {})


def test_combination_of_sources():

    def handler(a: FromQuery(List[str]),
                b: FromServices(Dog),
                c: FromJson(Cat),
                d: FromRoute(),
                e: FromHeader()):
        ...

    binders = get_binders(Route(b'/:d', handler), {
        Dog: Dog('Snoopy')
    })

    assert isinstance(binders[0], FromQuery)
    assert isinstance(binders[1], FromServices)
    assert isinstance(binders[2], FromJson)
    assert isinstance(binders[3], FromRoute)
    assert isinstance(binders[4], FromHeader)
    assert binders[0].name == 'a'
    assert binders[1].name == 'b'
    assert binders[2].name == 'c'
    assert binders[3].name == 'd'
    assert binders[4].name == 'e'


def test_from_query_specific_name():

    def handler(a: FromQuery(str, 'example')):
        ...

    binders = get_binders(Route(b'/', handler), {})

    assert isinstance(binders[0], FromQuery)
    assert binders[0].expected_type is str
    assert binders[0].name == 'example'


def test_from_header_specific_name():

    def handler(a: FromHeader(str, 'example')):
        ...

    binders = get_binders(Route(b'/', handler), {})

    assert isinstance(binders[0], FromHeader)
    assert binders[0].expected_type is str
    assert binders[0].name == 'example'


def test_raises_for_route_mismatch():

    def handler(a: FromRoute(str, 'missing_name')):
        ...

    with raises(RouteBinderMismatch):
        get_binders(Route(b'/', handler), {})


def test_request_binding():

    def handler(request):
        ...

    binders = get_binders(Route(b'/', handler), {})

    assert isinstance(binders[0], RequestBinder)


def test_services_binding():
    app_services = {}

    def handler(services):
        assert services is app_services

    binders = get_binders(Route(b'/', handler), app_services)

    assert isinstance(binders[0], ExactBinder)


@pytest.mark.asyncio
async def test_services_from_normalization():

    app_services = {}

    def handler(services):
        assert services is app_services
        return services

    method = normalize_handler(Route(b'/', handler), app_services)
    services = await method(None)
    assert services is app_services


async def fake_handler(_):
    return 'fake-handler-result'


@pytest.mark.asyncio
async def test_middleware_normalization():
    services = {'context': object()}
    fake_request = Request('GET', b'/', None)

    async def middleware(request, handler, context):
        assert request is fake_request
        assert handler is fake_handler
        assert context is services.get('context')
        return await handler(request)

    normalized = normalize_middleware(middleware, services)

    # NB: middlewares base signature is (request, handler)
    result = await normalized(fake_request, fake_handler)
    assert result == 'fake-handler-result'


@pytest.mark.asyncio
async def test_middleware_query_normalization():
    services = {'context': object()}
    fake_request = Request('GET', b'/?example=Lorem', None)

    async def middleware(request, handler, example: FromQuery(str)):
        assert request is fake_request
        assert handler is fake_handler
        assert example == 'Lorem'
        return await handler(request)

    normalized = normalize_middleware(middleware, services)

    # NB: middlewares base signature is (request, handler)
    result = await normalized(fake_request, fake_handler)
    assert result == 'fake-handler-result'


@pytest.mark.asyncio
async def test_middleware_header_normalization():
    services = {'context': object()}
    fake_request = Request('GET', b'/', [
        (b'example', b'Lorem')
    ])

    async def middleware(request, handler, example: FromHeader(str)):
        assert request is fake_request
        assert handler is fake_handler
        assert example == 'Lorem'
        return await handler(request)

    normalized = normalize_middleware(middleware, services)

    # NB: middlewares base signature is (request, handler)
    result = await normalized(fake_request, fake_handler)
    assert result == 'fake-handler-result'


@pytest.mark.asyncio
async def test_middleware_normalization_no_parameters():
    services = {'context': object()}
    fake_request = Request('GET', b'/', [
        (b'example', b'Lorem')
    ])

    called = False

    async def middleware():
        nonlocal called
        called = True

    normalized = normalize_middleware(middleware, services)

    # NB: middlewares base signature is (request, handler)
    # since our middleware above does not handle the next request handler, it is called by the normalized method
    result = await normalized(fake_request, fake_handler)
    assert called
    assert result == 'fake-handler-result'


def test_middleware_not_normalized_if_signature_matches_expected_signature():

    async def middleware(request, handler):
        return await handler(request)

    normalized = normalize_middleware(middleware, {})
    assert normalized is middleware
