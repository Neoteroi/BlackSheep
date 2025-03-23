import sys
from dataclasses import dataclass
from inspect import Parameter, _ParameterKind
from typing import AsyncIterable, List, Optional, Sequence, Union

import pytest
from guardpost import Identity, User
from pytest import raises
from rodi import Container, Services, inject

from blacksheep import Request
from blacksheep.server.bindings import (
    Binder,
    BoundValue,
    ExactBinder,
    FromHeader,
    FromJSON,
    FromQuery,
    FromRoute,
    FromServices,
    HeaderBinder,
    IdentityBinder,
    JSONBinder,
    QueryBinder,
    RequestBinder,
    RouteBinder,
    ServiceBinder,
)
from blacksheep.server.normalization import (
    AmbiguousMethodSignatureError,
    NormalizationError,
    RouteBinderMismatch,
    UnsupportedSignatureError,
    _check_union,
    _get_raw_bound_value_type,
    get_asyncgen_yield_type,
    get_binders,
    normalize_handler,
    normalize_middleware,
)
from blacksheep.server.routing import Route


class Pet:
    def __init__(self, name):
        self.name = name


class Cat(Pet): ...


class Dog(Pet): ...


@dataclass
class SomeService:
    pass


def test_parameters_get_binders_default_query():
    def handler(a, b, c): ...

    binders = get_binders(Route(b"/", handler), Container())

    assert all(isinstance(binder, QueryBinder) for binder in binders)
    assert binders[0].parameter_name == "a"
    assert binders[1].parameter_name == "b"
    assert binders[2].parameter_name == "c"


@pytest.mark.parametrize(
    "annotation_type", [Identity, User, Optional[User], Optional[Identity]]
)
def test_identity_binder_by_param_type(annotation_type):
    async def handler(param): ...

    handler.__annotations__["param"] = annotation_type

    binders = get_binders(Route(b"/", handler), Container())

    assert isinstance(binders[0], IdentityBinder)


def test_parameters_get_binders_from_route():
    def handler(a, b, c): ...

    binders = get_binders(Route(b"/:a/:b/:c", handler), Container())

    assert all(isinstance(binder, RouteBinder) for binder in binders)
    assert binders[0].parameter_name == "a"
    assert binders[1].parameter_name == "b"
    assert binders[2].parameter_name == "c"


def test_parameters_get_binders_from_services_by_name():
    def handler(a, b, c): ...

    binders = get_binders(
        Route(b"/", handler), {"a": object(), "b": object(), "c": object()}
    )

    assert all(isinstance(binder, ServiceBinder) for binder in binders)
    assert binders[0].expected_type == "a"
    assert binders[1].expected_type == "b"
    assert binders[2].expected_type == "c"


def test_parameters_get_binders_from_services_by_type():
    def handler(a: str, b: int, c: Cat): ...

    binders = get_binders(
        Route(b"/", handler), {str: object(), int: object(), Cat: object()}
    )

    assert all(isinstance(binder, ServiceBinder) for binder in binders)
    assert binders[0].expected_type is str
    assert binders[1].expected_type is int
    assert binders[2].expected_type is Cat


def test_parameters_get_binders_from_body():
    def handler(a: Cat): ...

    binders = get_binders(Route("/", handler), Container())
    assert len(binders) == 1
    binder = binders[0]

    assert isinstance(binder, JSONBinder)
    assert binder.expected_type is Cat
    assert binder.required is True


def test_parameters_get_binders_from_body_optional():
    def handler(a: Optional[Cat]): ...

    binders = get_binders(Route(b"/", handler), Container())
    assert len(binders) == 1
    binder = binders[0]

    assert isinstance(binder, JSONBinder)
    assert binder.expected_type is Cat
    assert binder.required is False


def test_parameters_get_binders_simple_types_default_from_query():
    def handler(a: str, b: int, c: bool): ...

    binders = get_binders(Route(b"/", handler), Container())

    assert all(isinstance(binder, QueryBinder) for binder in binders)
    assert binders[0].parameter_name == "a"
    assert binders[0].expected_type == str
    assert binders[1].parameter_name == "b"
    assert binders[1].expected_type == int
    assert binders[2].parameter_name == "c"
    assert binders[2].expected_type == bool


def test_parameters_get_binders_list_types_default_from_query():
    def handler(a: List[str], b: List[int], c: List[bool]): ...

    binders = get_binders(Route(b"/", handler), Container())

    assert all(isinstance(binder, QueryBinder) for binder in binders)
    assert binders[0].parameter_name == "a"
    assert binders[0].expected_type == List[str]
    assert binders[1].parameter_name == "b"
    assert binders[1].expected_type == List[int]
    assert binders[2].parameter_name == "c"
    assert binders[2].expected_type == List[bool]


def test_parameters_get_binders_list_types_default_from_query_optional():
    def handler(a: Optional[List[str]]): ...

    binders = get_binders(Route(b"/", handler), Container())

    assert all(isinstance(binder, QueryBinder) for binder in binders)
    assert all(binder.required is False for binder in binders)
    assert binders[0].parameter_name == "a"
    assert binders[0].expected_type == List[str]


def test_parameters_get_binders_list_types_default_from_query_required():
    def handler(a: List[str]): ...

    binders = get_binders(Route(b"/", handler), Container())

    assert all(isinstance(binder, QueryBinder) for binder in binders)
    assert all(binder.required for binder in binders)


def test_parameters_get_binders_sequence_types_default_from_query():
    def handler(a: Sequence[str], b: Sequence[int], c: Sequence[bool]): ...

    binders = get_binders(Route(b"/", handler), Container())

    assert all(isinstance(binder, QueryBinder) for binder in binders)
    assert binders[0].parameter_name == "a"
    assert binders[0].expected_type == Sequence[str]
    assert binders[1].parameter_name == "b"
    assert binders[1].expected_type == Sequence[int]
    assert binders[2].parameter_name == "c"
    assert binders[2].expected_type == Sequence[bool]


def test_throw_for_ambiguous_binder_multiple_from_body():
    def handler(a: Cat, b: Dog): ...

    with pytest.raises(AmbiguousMethodSignatureError):
        get_binders(Route(b"/", handler), Container())


def test_does_not_throw_for_forward_ref():
    def handler(a: "Cat"): ...

    get_binders(Route(b"/", handler), Container())

    def handler(a: List["str"]): ...

    get_binders(Route(b"/", handler), Container())

    def handler(a: Optional[List["Cat"]]): ...

    get_binders(Route(b"/", handler), Container())

    def handler(a: FromQuery["str"]): ...

    get_binders(Route(b"/", handler), Container())


def test_combination_of_sources():
    def handler(
        a: FromQuery[List[str]],
        b: FromServices[Dog],
        c: FromJSON[Cat],
        d: FromRoute[str],
        e: FromHeader[str],
    ): ...

    container = Container()
    container.register(Dog, instance=Dog("Snoopy"))
    binders = get_binders(Route(b"/:d", handler), container)

    assert isinstance(binders[0], QueryBinder)
    assert isinstance(binders[1], ServiceBinder)
    assert isinstance(binders[2], JSONBinder)
    assert isinstance(binders[3], RouteBinder)
    assert isinstance(binders[4], HeaderBinder)
    assert binders[0].parameter_name == "a"
    assert binders[1].parameter_name == "b"
    assert binders[2].parameter_name == "c"
    assert binders[3].parameter_name == "d"
    assert binders[4].parameter_name == "e"


def test_implicit_from_services_only_when_annotation_is_none():
    def handler(dog): ...

    container = Container()
    container.register("dog", instance=Dog("Snoopy"))

    binders = get_binders(Route(b"/", handler), container)

    assert isinstance(binders[0], ServiceBinder)

    def handler(dog: str): ...

    binders = get_binders(Route(b"/", handler), container)

    assert isinstance(binders[0], QueryBinder)


def test_from_query_specific_name():
    class FromExampleQuery(FromQuery[str]):
        name = "example"

    @inject()
    def handler(a: FromExampleQuery): ...

    binders = get_binders(Route(b"/", handler), Container())
    binder = binders[0]

    assert isinstance(binder, QueryBinder)
    assert binder.expected_type is str
    assert binder.required is True
    assert binder.parameter_name == "example"


def test_from_query_unspecified_type():
    def handler(a: FromQuery): ...

    binders = get_binders(Route(b"/", handler), Container())
    binder = binders[0]

    assert isinstance(binder, QueryBinder)
    assert binder.expected_type is List[str]
    assert binder.required is True
    assert binder.parameter_name == "a"


def test_from_query_optional_type():
    def handler(a: FromQuery[Optional[str]]): ...

    binders = get_binders(Route(b"/", handler), Container())
    binder = binders[0]

    assert isinstance(binder, QueryBinder)
    assert binder.expected_type is str
    assert binder.required is False
    assert binder.parameter_name == "a"


def test_from_query_optional_type_with_union():
    def handler(a: FromQuery[Union[None, str]]): ...

    binders = get_binders(Route(b"/", handler), Container())
    binder = binders[0]

    assert isinstance(binder, QueryBinder)
    assert binder.expected_type is str
    assert binder.required is False
    assert binder.parameter_name == "a"


def test_check_union():
    optional, value = _check_union(
        Parameter("foo", kind=_ParameterKind.POSITIONAL_ONLY),
        Union[None, str],
        len,
    )
    assert optional is True
    assert value is str


@pytest.mark.skipif(sys.version_info < (3, 10), reason="requires python3.10 or higher")
def test_check_union_or_none():
    optional, value = _check_union(
        Parameter("foo", kind=_ParameterKind.POSITIONAL_ONLY),
        str | None,
        len,
    )
    assert optional is True
    assert value is str


def test_from_query_optional_list_type():
    def handler(a: FromQuery[Optional[List[str]]]): ...

    binders = get_binders(Route(b"/", handler), Container())
    binder = binders[0]

    assert isinstance(binder, QueryBinder)
    assert binder.expected_type is List[str]
    assert binder.required is False
    assert binder.parameter_name == "a"


def test_from_header_specific_name():
    class FromExampleHeader(FromHeader[str]):
        name = "example"

    @inject()
    def handler(a: FromExampleHeader): ...

    binders = get_binders(Route(b"/", handler), Container())

    assert isinstance(binders[0], HeaderBinder)
    assert binders[0].expected_type is str
    assert binders[0].parameter_name == "example"


def test_from_header_accept_language_example():
    class AcceptLanguageHeader(FromHeader[str]):
        name = "accept-language"

    @inject()
    def handler(a: AcceptLanguageHeader): ...

    binders = get_binders(Route(b"/", handler), Container())

    assert isinstance(binders[0], HeaderBinder)
    assert binders[0].expected_type is str
    assert binders[0].parameter_name == "accept-language"


def test_raises_for_route_mismatch():
    def handler(a: FromRoute[str]): ...

    with raises(RouteBinderMismatch):
        get_binders(Route(b"/", handler), Container())


def test_raises_for_route_mismatch_2():
    def handler(a: FromRoute[str]): ...

    with raises(RouteBinderMismatch):
        get_binders(Route(b"/:b", handler), Container())


def test_raises_for_unsupported_union():
    def handler(a: FromRoute[Union[str, int]]): ...

    with raises(NormalizationError):
        get_binders(Route(b"/:b", handler), Container())


def test_request_binding():
    def handler(request): ...

    binders = get_binders(Route(b"/", handler), Container())

    assert isinstance(binders[0], RequestBinder)


def test_services_binding():
    app_services = Container()

    def handler(services):
        assert services is app_services

    binders = get_binders(Route(b"/", handler), app_services)

    assert isinstance(binders[0], ExactBinder)


async def test_services_from_normalization():
    app_services = Container()

    def handler(services):
        assert services is app_services
        return None

    method = normalize_handler(Route(b"/", handler), app_services)
    await method(None)


def test_raises_for_unsupported_signature():
    app_services = Container()

    def handler(services, *args):
        assert services is app_services
        return services

    def handler2(services, **kwargs):
        assert services is app_services
        return services

    def handler3(services, *, key_only):
        assert services is app_services
        return services

    with pytest.raises(UnsupportedSignatureError):
        normalize_handler(Route(b"/", handler), Container())

    with pytest.raises(UnsupportedSignatureError):
        normalize_handler(Route(b"/", handler2), Container())

    with pytest.raises(UnsupportedSignatureError):
        normalize_handler(Route(b"/", handler3), Container())


async def fake_handler(_):
    return "fake-handler-result"


async def test_middleware_normalization():
    container = Container()
    container.add_singleton(object)
    container.add_alias("context", object)

    fake_request = Request("GET", b"/", None)

    async def middleware(request, handler, context: object):
        assert request is fake_request
        assert handler is fake_handler
        assert context is container.resolve("context")
        return await handler(request)

    normalized = normalize_middleware(middleware, container)

    # NB: middlewares base signature is (request, handler)
    result = await normalized(fake_request, fake_handler)  # type: ignore
    assert result == "fake-handler-result"


async def test_middleware_normalization_2():
    services = Container()  # {"context": object(), "foo": object()}
    fake_request = Request("GET", b"/", None)

    async def middleware(context, foo):
        pass

    normalized = normalize_middleware(middleware, services)  # type: ignore

    # NB: middlewares base signature is (request, handler)
    result = await normalized(fake_request, fake_handler)  # type: ignore
    assert result == "fake-handler-result"


async def test_middleware_normalization_raises_for_sync_function():
    def faulty_middleware(request, handler):
        pass

    with pytest.raises(ValueError):
        normalize_middleware(faulty_middleware, Services())  # type: ignore


async def test_middleware_query_normalization():
    container = Container()
    container.register("context", instance=object())

    fake_request = Request("GET", b"/?example=Lorem", None)

    async def middleware(request, handler, example: FromQuery[str]):
        assert request is fake_request
        assert handler is fake_handler
        assert example.value == "Lorem"
        return await handler(request)

    normalized = normalize_middleware(middleware, container)

    # NB: middlewares base signature is (request, handler)
    result = await normalized(fake_request, fake_handler)  # type: ignore
    assert result == "fake-handler-result"


async def test_middleware_header_normalization():
    container = Container()
    container.register("context", instance=object())
    fake_request = Request("GET", b"/", [(b"example", b"Lorem")])

    async def middleware(request, handler, example: FromHeader[str]):
        assert request is fake_request
        assert handler is fake_handler
        assert example.value == "Lorem"
        return await handler(request)

    normalized = normalize_middleware(middleware, container)

    # NB: middlewares base signature is (request, handler)
    result = await normalized(fake_request, fake_handler)  # type: ignore
    assert result == "fake-handler-result"


async def test_middleware_normalization_no_parameters():
    container = Container()
    container.register("context", instance=object())
    fake_request = Request("GET", b"/", [(b"example", b"Lorem")])

    called = False

    async def middleware():
        nonlocal called
        called = True

    normalized = normalize_middleware(middleware, container)  # type: ignore

    # NB: middlewares base signature is (request, handler)
    # since our middleware above does not handle the next request handler,
    # it is called by the normalized method
    result = await normalized(fake_request, fake_handler)  # type: ignore
    assert called
    assert result == "fake-handler-result"


def test_middleware_not_normalized_if_signature_matches_expected_signature():
    async def middleware(request, handler):
        return await handler(request)

    normalized = normalize_middleware(middleware, Container())
    assert normalized is middleware


def test_get_raw_bound_value_type_fallsback_to_str():
    class Foo: ...

    assert _get_raw_bound_value_type(Foo) is str  # type: ignore


def test_normalization_with_service_json_route_param():
    def handler(
        foo_id: str,
        data: FromJSON[Cat],
        some_service: SomeService,
    ): ...

    container = Container()
    container.add_transient(SomeService)

    binders = get_binders(Route("/{foo_id}", handler), container)
    assert len(binders) == 3

    assert isinstance(binders[0], RouteBinder)
    assert binders[0].expected_type is str

    assert isinstance(binders[1], JSONBinder)
    assert binders[1].expected_type is Cat

    assert isinstance(binders[2], ServiceBinder)
    assert binders[2].expected_type is SomeService


def test_camel_case_route_parameter():
    def handler(statusKey: FromRoute[str]): ...

    binders = get_binders(Route(b"/:statusKey", handler), Container())

    assert isinstance(binders[0], RouteBinder)
    assert binders[0].parameter_name == "statusKey"


def test_pascal_case_route_parameter():
    def handler(StatusKey: FromRoute[str]): ...

    binders = get_binders(Route(b"/:StatusKey", handler), Container())

    assert isinstance(binders[0], RouteBinder)
    assert binders[0].parameter_name == "StatusKey"


async def test_binder_through_di():
    """
    Tests support for dependency injection when resolving custom binders.
    """

    class Foo: ...

    class FromExample(BoundValue[str]):
        pass

    class DIBinder(Binder):
        handle = FromExample

        def __init__(self, foo: Foo):
            super().__init__(str)
            self.foo = foo

        async def get_value(self, request: Request) -> Optional[str]:
            assert isinstance(self.foo, Foo)
            return "Foo!"

    def handler(example: FromExample):
        assert example.value == "Foo!"
        return example.value

    container = Container()
    container.register(Foo)
    container.register(DIBinder)

    binders = get_binders(Route("/", handler), container)
    assert len(binders) == 1

    assert isinstance(binders[0], DIBinder)

    fake_request = Request("GET", b"/", None)

    method = normalize_handler(Route(b"/", handler), container)
    response = await method(fake_request)
    assert response is not None
    text = await response.text()
    assert text == "Foo!"


def test_get_asyncgen_yield_type():
    async def example_1(data: str) -> AsyncIterable[int]:
        for i in range(10):
            yield i

    async def example_2() -> AsyncIterable[str]:
        for i in range(10):
            yield str(i)

    assert get_asyncgen_yield_type(example_1) is int
    assert get_asyncgen_yield_type(example_2) is str
