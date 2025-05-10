from typing import Any, List, Optional, Sequence, Set, Tuple, Type
from uuid import UUID

import pytest
from guardpost import Identity
from pytest import raises
from rodi import Container

from blacksheep import FormContent, FormPart, JSONContent, MultiPartFormData, Request
from blacksheep.server.bindings import (
    BadRequest,
    Binder,
    BinderAlreadyDefinedException,
    BinderNotRegisteredForValueType,
    BodyBinder,
    BoundValue,
    CookieBinder,
    FormBinder,
    HeaderBinder,
    IdentityBinder,
    InvalidRequestBody,
    JSONBinder,
    MissingBodyError,
    MissingConverterError,
    NameAliasAlreadyDefinedException,
    QueryBinder,
    RequestMethodBinder,
    RequestURLBinder,
    RouteBinder,
    ServiceBinder,
    SyncBinder,
    TypeAliasAlreadyDefinedException,
    get_binder_by_type,
)
from blacksheep.url import URL

JSONContentType = (b"Content-Type", b"application/json")


class ExampleOne:
    def __init__(self, a, b):
        self.a = a
        self.b = int(b)


class ExampleTwo:
    def __init__(self, a, b, **kwargs):
        self.a = a
        self.b = b


class ExampleThree:
    def __init__(self, a: str, b: List[str]):
        self.a = a
        self.b = b


async def test_from_body_json_binding():
    request = Request("POST", b"/", [JSONContentType]).with_content(
        JSONContent({"a": "world", "b": 9000})
    )

    parameter = JSONBinder(ExampleOne)

    value = await parameter.get_value(request)

    assert isinstance(value, ExampleOne)
    assert value.a == "world"
    assert value.b == 9000


async def test_from_body_json_binding_extra_parameters_strategy():
    request = Request("POST", b"/", [JSONContentType]).with_content(
        JSONContent(
            {
                "a": "world",
                "b": 9000,
                "c": "This is an extra parameter, accepted by constructor explicitly",
            }
        )
    )

    parameter = JSONBinder(ExampleTwo)

    value = await parameter.get_value(request)

    assert isinstance(value, ExampleTwo)
    assert value.a == "world"
    assert value.b == 9000


async def test_from_body_json_with_converter():
    request = Request("POST", b"/", [JSONContentType]).with_content(
        JSONContent(
            {
                "a": "world",
                "b": 9000,
                "c": "This is an extra parameter, accepted by constructor explicitly",
            }
        )
    )

    def convert(data):
        return ExampleOne(data.get("a"), data.get("b"))

    parameter = JSONBinder(ExampleOne, converter=convert)

    value = await parameter.get_value(request)

    assert isinstance(value, ExampleOne)
    assert value.a == "world"
    assert value.b == 9000


async def test_from_body_json_binding_request_missing_content_type():
    request = Request("POST", b"/", [])

    parameter = JSONBinder(ExampleOne)

    value = await parameter.get_value(request)

    assert value is None


async def test_from_body_json_binding_invalid_input():
    request = Request("POST", b"/", [JSONContentType]).with_content(
        JSONContent({"c": 1, "d": 2})
    )

    parameter = JSONBinder(ExampleOne)

    with raises(BadRequest):
        await parameter.get_value(request)


@pytest.mark.parametrize(
    "expected_type,header_value,expected_value",
    [
        [str, b"Foo", "Foo"],
        [str, b"foo", "foo"],
        [str, b"\xc5\x81ukasz", "Łukasz"],
        [str, b"Hello%20World%21%3F", "Hello World!?"],
        [int, b"1", 1],
        [int, b"10", 10],
        [float, b"1.5", 1.5],
        [float, b"1241.5", 1241.5],
        [bool, b"1", True],
        [bool, b"0", False],
    ],
)
async def test_from_header_binding(expected_type, header_value, expected_value):
    request = Request("GET", b"/", [(b"X-Foo", header_value)])

    parameter = HeaderBinder(expected_type, "X-Foo")

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value == expected_value


@pytest.mark.parametrize(
    "expected_type,header_value,expected_value",
    [
        [str, b"Foo", "Foo"],
        [str, b"foo", "foo"],
        [str, b"\xc5\x81ukasz", "Łukasz"],
        [str, b"Hello%20World%21%3F", "Hello World!?"],
        [int, b"1", 1],
        [int, b"10", 10],
        [float, b"1.5", 1.5],
        [float, b"1241.5", 1241.5],
        [bool, b"1", True],
        [bool, b"0", False],
    ],
)
async def test_from_header_binding_name_ci(expected_type, header_value, expected_value):
    request = Request("GET", b"/", [(b"X-Foo", header_value)])

    parameter = HeaderBinder(expected_type, "x-foo")

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value == expected_value


@pytest.mark.parametrize(
    "expected_type,query_value,expected_value",
    [
        [str, b"Foo", "Foo"],
        [str, b"foo", "foo"],
        [str, b"Hello%20World%21%3F", "Hello World!?"],
        [int, b"1", 1],
        [int, b"10", 10],
        [float, b"1.5", 1.5],
        [float, b"1241.5", 1241.5],
        [bool, b"1", True],
        [bool, b"0", False],
    ],
)
async def test_from_query_binding(expected_type, query_value, expected_value):
    request = Request("GET", b"/?foo=" + query_value, None)

    parameter = QueryBinder(expected_type, "foo")

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value == expected_value


@pytest.mark.parametrize(
    "expected_type,route_value,expected_value",
    [
        [str, "Foo", "Foo"],
        [str, "foo", "foo"],
        [str, "Hello%20World%21%3F", "Hello World!?"],
        [int, "1", 1],
        [int, "10", 10],
        [float, "1.5", 1.5],
        [float, "1241.5", 1241.5],
        [bool, "1", True],
        [bool, "0", False],
        [
            UUID,
            "b0c1f822-b63c-475e-9f2e-b6406bafcc2b",
            UUID("b0c1f822-b63c-475e-9f2e-b6406bafcc2b"),
        ],
    ],
)
async def test_from_route_binding(expected_type, route_value, expected_value):
    request = Request("GET", b"/", None)
    request.route_values = {"name": route_value}

    parameter = RouteBinder(expected_type, "name")

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value == expected_value


@pytest.mark.parametrize("binder_type", [HeaderBinder, QueryBinder, RouteBinder])
async def test_raises_for_missing_default_converter(binder_type):
    with raises(MissingConverterError):
        binder_type("example", ExampleOne)


@pytest.mark.parametrize(
    "expected_type,invalid_value",
    [[int, "x"], [int, ""], [float, "x"], [float, ""], [bool, "x"], [bool, "yes"]],
)
async def test_from_route_raises_for_invalid_parameter(expected_type, invalid_value):
    request = Request("GET", b"/", None)
    request.route_values = {"name": invalid_value}

    parameter = RouteBinder(expected_type, "name")

    with raises(BadRequest):
        await parameter.get_value(request)


@pytest.mark.parametrize(
    "expected_type,invalid_value",
    [
        [int, b"x"],
        [int, b""],
        [float, b"x"],
        [float, b""],
        [bool, b"x"],
        [bool, b"yes"],
    ],
)
async def test_from_query_raises_for_invalid_parameter(
    expected_type, invalid_value: bytes
):
    request = Request("GET", b"/?foo=" + invalid_value, None)

    parameter = QueryBinder(expected_type, "foo", required=True)

    with raises(BadRequest):
        await parameter.get_value(request)


async def test_from_services():
    request = Request("GET", b"/", [])

    service_instance = ExampleOne(1, 2)
    container = Container()
    container.add_instance(service_instance)

    parameter = ServiceBinder(ExampleOne, "service", False, container)
    value = await parameter.get_value(request)

    assert value is service_instance


@pytest.mark.parametrize(
    "declared_type,expected_type,header_values,expected_values",
    [
        [List[str], list, [b"Lorem", b"ipsum", b"dolor"], ["Lorem", "ipsum", "dolor"]],
        [
            Tuple[str],
            tuple,
            [b"Lorem", b"ipsum", b"dolor"],
            ("Lorem", "ipsum", "dolor"),
        ],
        [Set[str], set, [b"Lorem", b"ipsum", b"dolor"], {"Lorem", "ipsum", "dolor"}],
        [
            Sequence[str],
            list,
            [b"Lorem", b"ipsum", b"dolor"],
            ["Lorem", "ipsum", "dolor"],
        ],
    ],
)
async def test_from_header_binding_iterables(
    declared_type, expected_type, header_values, expected_values
):
    request = Request("GET", b"/", [(b"X-Foo", value) for value in header_values])

    parameter = HeaderBinder(declared_type, "X-Foo")

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value == expected_values


@pytest.mark.parametrize(
    "declared_type,expected_type,query_values,expected_values",
    [
        [list, list, [b"Lorem", b"ipsum", b"dolor"], ["Lorem", "ipsum", "dolor"]],
        [tuple, tuple, [b"Lorem", b"ipsum", b"dolor"], ("Lorem", "ipsum", "dolor")],
        [set, set, [b"Lorem", b"ipsum", b"dolor"], {"Lorem", "ipsum", "dolor"}],
        [List, list, [b"Lorem", b"ipsum", b"dolor"], ["Lorem", "ipsum", "dolor"]],
        [Tuple, tuple, [b"Lorem", b"ipsum", b"dolor"], ("Lorem", "ipsum", "dolor")],
        [Set, set, [b"Lorem", b"ipsum", b"dolor"], {"Lorem", "ipsum", "dolor"}],
        [List[str], list, [b"Lorem", b"ipsum", b"dolor"], ["Lorem", "ipsum", "dolor"]],
        [
            Tuple[str],
            tuple,
            [b"Lorem", b"ipsum", b"dolor"],
            ("Lorem", "ipsum", "dolor"),
        ],
        [Set[str], set, [b"Lorem", b"ipsum", b"dolor"], {"Lorem", "ipsum", "dolor"}],
        [
            Sequence[str],
            list,
            [b"Lorem", b"ipsum", b"dolor"],
            ["Lorem", "ipsum", "dolor"],
        ],
        [List[int], list, [b"10"], [10]],
        [List[int], list, [b"0", b"1", b"0"], [0, 1, 0]],
        [List[int], list, [b"0", b"1", b"0", b"2"], [0, 1, 0, 2]],
        [list[int], list, [b"0", b"1", b"0", b"2"], [0, 1, 0, 2]],
        [List[bytes], list, [b"0", b"1", b"0", b"2"], [b"0", b"1", b"0", b"2"]],
        [List[bool], list, [b"1"], [True]],
        [List[bool], list, [b"0", b"1", b"0"], [False, True, False]],
        [List[bool], list, [b"0", b"1", b"0", b"true"], [False, True, False, True]],
        [list[bool], list, [b"0", b"1", b"0", b"true"], [False, True, False, True]],
        [List[float], list, [b"10.2"], [10.2]],
        [List[float], list, [b"0.3", b"1", b"0"], [0.3, 1.0, 0]],
        [List[float], list, [b"0.5", b"1", b"0", b"2"], [0.5, 1.0, 0, 2.0]],
        [list[float], list, [b"0.5", b"1", b"0", b"2"], [0.5, 1.0, 0, 2.0]],
        [Tuple[float], tuple, [b"10.2"], (10.2,)],
        [Tuple[float], tuple, [b"0.3", b"1", b"0"], (0.3, 1.0, 0)],
        [Tuple[float], tuple, [b"0.5", b"1", b"0", b"2"], (0.5, 1.0, 0, 2.0)],
        [tuple[float], tuple, [b"0.5", b"1", b"0", b"2"], (0.5, 1.0, 0, 2.0)],
        [Set[int], set, [b"10"], {10}],
        [Set[int], set, [b"0", b"1", b"0"], {0, 1, 0}],
        [Set[int], set, [b"0", b"1", b"0", b"2"], {0, 1, 0, 2}],
        [set[int], set, [b"0", b"1", b"0", b"2"], {0, 1, 0, 2}],
        [
            List[UUID],
            list,
            [
                b"de18d268-f5c5-42db-89b2-c61bbfe96e65",
                b"d5fd0cde-4ad6-4b61-a5b1-5b8e6d48cebe",
                b"00000000-0000-0000-0000-000000000000",
            ],
            [
                UUID("de18d268-f5c5-42db-89b2-c61bbfe96e65"),
                UUID("d5fd0cde-4ad6-4b61-a5b1-5b8e6d48cebe"),
                UUID("00000000-0000-0000-0000-000000000000"),
            ],
        ],
        [
            list[UUID],
            list,
            [
                b"de18d268-f5c5-42db-89b2-c61bbfe96e65",
                b"d5fd0cde-4ad6-4b61-a5b1-5b8e6d48cebe",
                b"00000000-0000-0000-0000-000000000000",
            ],
            [
                UUID("de18d268-f5c5-42db-89b2-c61bbfe96e65"),
                UUID("d5fd0cde-4ad6-4b61-a5b1-5b8e6d48cebe"),
                UUID("00000000-0000-0000-0000-000000000000"),
            ],
        ],
    ],
)
async def test_from_query_binding_iterables(
    declared_type, expected_type, query_values, expected_values
):
    qs = b"&foo=".join([value for value in query_values])

    request = Request("GET", b"/?foo=" + qs, None)

    parameter = QueryBinder(declared_type, "foo")

    values = await parameter.get_value(request)

    assert isinstance(values, expected_type)
    assert values == expected_values


@pytest.mark.parametrize(
    "declared_type", [List[List[str]], Tuple[Tuple[str]], List[list]]
)
async def test_nested_iterables_raise_missing_converter_from_header(declared_type):
    with raises(MissingConverterError):
        HeaderBinder(declared_type)


@pytest.mark.parametrize(
    "declared_type", [List[List[str]], Tuple[Tuple[str]], List[list]]
)
async def test_nested_iterables_raise_missing_converter_from_query(declared_type):
    with raises(MissingConverterError):
        QueryBinder("example", declared_type)


async def test_identity_binder_identity_not_set():
    request = Request("GET", b"/", None)

    parameter = IdentityBinder(Identity)

    value = await parameter.get_value(request)

    assert value is None


async def test_identity_binder():
    request = Request("GET", b"/", None)
    request.user = Identity({})

    parameter = IdentityBinder(Identity)

    value = await parameter.get_value(request)

    assert value is request.user


async def test_from_body_form_binding_urlencoded():
    request = Request("POST", b"/", []).with_content(
        FormContent({"a": "world", "b": 9000})
    )

    parameter = FormBinder(ExampleOne)

    value = await parameter.get_value(request)

    assert isinstance(value, ExampleOne)
    assert value.a == "world"
    assert value.b == 9000


async def test_from_body_form_binding_urlencoded_keys_duplicates():
    request = Request("POST", b"/", []).with_content(
        FormContent([("a", "world"), ("b", "one"), ("b", "two"), ("b", "three")])
    )

    parameter = FormBinder(ExampleThree)

    value = await parameter.get_value(request)

    assert isinstance(value, ExampleThree)
    assert value.a == "world"
    assert value.b == ["one", "two", "three"]


async def test_from_body_form_binding_multipart():
    request = Request("POST", b"/", []).with_content(
        MultiPartFormData([FormPart(b"a", b"world"), FormPart(b"b", b"9000")])
    )

    parameter = FormBinder(ExampleOne)
    value = await parameter.get_value(request)

    assert isinstance(value, ExampleOne)
    assert value.a == "world"
    assert value.b == 9000


async def test_from_body_form_binding_multipart_keys_duplicates():
    request = Request("POST", b"/", []).with_content(
        MultiPartFormData(
            [
                FormPart(b"a", b"world"),
                FormPart(b"b", b"one"),
                FormPart(b"b", b"two"),
                FormPart(b"b", b"three"),
            ]
        )
    )

    parameter = FormBinder(ExampleThree)

    value = await parameter.get_value(request)

    assert isinstance(value, ExampleThree)
    assert value.a == "world"
    assert value.b == ["one", "two", "three"]


async def test_custom_bound_value_and_binder():
    class FromMethod(BoundValue[str]):
        pass

    class MethodBinder(Binder):
        handle = FromMethod

        async def get_value(self, request: Request) -> Optional[str]:
            return request.method

    parameter = MethodBinder(str)

    for method in {"GET", "POST", "TRACE"}:
        value = await parameter.get_value(Request(method, b"/", []))
        assert value == method


async def test_custom_bound_value_fails_for_missing_binder():
    class FromSomething(BoundValue[str]):
        pass

    def faulty(example: FromSomething):
        pass

    with pytest.raises(BinderNotRegisteredForValueType):
        get_binder_by_type(FromSomething)


async def test_raises_for_duplicate_binders():
    class FromMethod(BoundValue[str]):
        pass

    class MethodBinder(Binder):
        handle = FromMethod

        async def get_value(self, request: Request) -> Optional[str]:
            return request.method

    with pytest.raises(BinderAlreadyDefinedException):

        class MethodBinder2(Binder):
            handle = FromMethod

            async def get_value(self, request: Request) -> Optional[str]:
                return request.method


@pytest.mark.parametrize(
    "binder_type,expected_source_name",
    [(RouteBinder, "route"), (QueryBinder, "query"), (HeaderBinder, "header")],
)
def test_sync_binder_source_name(
    binder_type: Type[SyncBinder], expected_source_name: str
):
    binder = binder_type(str)
    assert binder.source_name == expected_source_name


async def test_body_binder_throws_for_abstract_methods():
    body_binder = BodyBinder(dict)

    with pytest.raises(NotImplementedError):
        body_binder.matches_content_type(Request("HEAD", b"/", []))

    with pytest.raises(NotImplementedError):
        await body_binder.read_data(Request("HEAD", b"/", []))


async def test_body_binder_throws_bad_request_for_missing_body():
    class CustomBodyBinder(BodyBinder):
        def matches_content_type(self, request: Request) -> bool:
            return True

        async def read_data(self, request: Request) -> Any:
            return None

    body_binder = CustomBodyBinder(dict)

    with pytest.raises(MissingBodyError):
        await body_binder.get_value(
            Request("POST", b"/", [(b"content-type", b"application/json")])
        )

    body_binder = JSONBinder(dict, required=True)

    with pytest.raises(MissingBodyError):
        await body_binder.get_value(Request("POST", b"/", []))


async def test_body_binder_throws_bad_request_for_value_error():
    body_binder = JSONBinder(dict, required=True)

    def example_converter(value):
        raise ValueError("Invalid value")

    body_binder.converter = example_converter

    with pytest.raises(InvalidRequestBody):
        await body_binder.get_value(
            Request(
                "POST", b"/", [(b"content-type", b"application/json")]
            ).with_content(JSONContent({"id": "1", "name": "foo"}))
        )


def test_sync_binders_source_name():
    assert CookieBinder().source_name == "cookie"
    assert HeaderBinder().source_name == "header"
    assert QueryBinder().source_name == "query"
    assert RouteBinder().source_name == "route"


@pytest.mark.parametrize("method", ["GET", "OPTIONS", "POST"])
async def test_request_method_binder(method):
    request = Request(method, b"/", [])
    parameter = RequestMethodBinder()
    value = await parameter.get_value(request)
    assert value == method


@pytest.mark.parametrize("url", [b"/", b"/api/cats/123", b"/foo/index.html?s=20"])
async def test_request_url_binder(url):
    request = Request("GET", url, [])
    parameter = RequestURLBinder()
    value = await parameter.get_value(request)
    assert value == URL(url)


def test_duplicate_name_alias_raises():
    class FooBinder1(Binder):
        name_alias = "foo_absurd_example"

    with pytest.raises(NameAliasAlreadyDefinedException) as duplicate_alias_error:

        class FooBinder2(Binder):
            name_alias = "foo_absurd_example"

    assert str(duplicate_alias_error.value) == (
        "There is already a name alias defined for 'foo_absurd_example', "
        "the second type is: FooBinder2"
    )


def test_duplicate_type_alias_raises():
    class X:
        pass

    class XBinder1(Binder):
        type_alias = X

    with pytest.raises(TypeAliasAlreadyDefinedException) as duplicate_alias_error:

        class XBinder2(Binder):
            type_alias = X

    assert str(duplicate_alias_error.value) == (
        "There is already a type alias defined for 'X', the second type is: XBinder2"
    )
