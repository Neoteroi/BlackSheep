import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Literal, Sequence, Set, Tuple, Type
from uuid import UUID

import pytest
from guardpost import Identity
from pydantic import BaseModel
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


ExampleLiteralStr = Literal["Hello", "World"]
ExampleLiteralInt = Literal[1, 2, 3]


try:
    # Supported only in Python >= 3.11
    from enum import IntEnum, StrEnum
except ImportError:

    class StrEnum: ...

    class IntEnum: ...


class ExampleOne:
    def __init__(self, a, b):
        self.a = a
        self.b = int(b)


@dataclass
class ExampleDataClass:
    a: str
    b: int


class ExampleTwo:
    def __init__(self, a, b, **kwargs):
        self.a = a
        self.b = b


class ExampleThree:
    def __init__(self, a: str, b: list[str]):
        self.a = a
        self.b = b


class ExampleStrEnum(StrEnum):
    ONE = "one"
    TWO = "two"
    THREE = "three"


class ExampleIntEnum(IntEnum):
    ONE = 1
    TWO = 2
    THREE = 3


class ExamplePydanticModel(BaseModel):
    a: str
    b: int


# Example plain classes


class ContactInfo:
    def __init__(self, phone: str, email: str, created_at: datetime):
        self.phone = phone
        self.email = email
        self.created_at = created_at


class PlainAddress:
    def __init__(self, street: str, city: str, zip_code: str):
        self.street = street
        self.city = city
        self.zip_code = zip_code


class PlainUser:
    def __init__(self, name: str, email: str, age: int, address: PlainAddress):
        self.name = name
        self.email = email
        self.age = age
        self.address = address


class PlainUser2:
    def __init__(self, name: str, email: str, age: int, addresses: list[PlainAddress]):
        self.name = name
        self.email = email
        self.age = age
        self.addresses = addresses


class PlainUserWithContacts:
    def __init__(
        self, name: str, email: str, age: int, contacts: dict[str, ContactInfo]
    ):
        self.name = name
        self.email = email
        self.age = age
        self.contacts = contacts


class PlainUserWithContactsUUID:
    def __init__(
        self, name: str, email: str, age: int, contacts: dict[UUID, ContactInfo]
    ):
        self.name = name
        self.email = email
        self.age = age
        self.contacts = contacts


class ContactInfoModel(BaseModel):
    phone: str
    email: str
    created_at: datetime


class AddressModel(BaseModel):
    street: str
    city: str
    zip_code: str


class UserModel(BaseModel):
    name: str
    email: str
    age: int
    address: AddressModel


class UserModel2(BaseModel):
    name: str
    email: str
    age: int
    addresses: list[AddressModel]


class UserModelWithContacts(BaseModel):
    name: str
    email: str
    age: int
    contacts: dict[str, ContactInfoModel]


class UserModelWithContactsUUID(BaseModel):
    name: str
    email: str
    age: int
    contacts: dict[UUID, ContactInfoModel]


@dataclass
class AddressDc:
    street: str
    city: str
    zip_code: str


@dataclass
class ContactInfoDc:
    phone: str
    email: str
    created_at: datetime


@dataclass
class UserDc:
    name: str
    email: str
    age: int
    address: AddressDc


@dataclass
class UserDcMix:
    name: str
    email: str
    age: int
    address: AddressModel


@dataclass
class UserDcWithContacts:
    name: str
    email: str
    age: int
    contacts: dict[str, ContactInfoDc]


@dataclass
class UserDcWithContactsUUID:
    name: str
    email: str
    age: int
    contacts: dict[UUID, ContactInfoDc]


@dataclass
class UserDc2:
    name: str
    email: str
    age: int
    addresses: list[AddressDc]


@dataclass
class UserDc2Mix:
    name: str
    email: str
    age: int
    addresses: list[AddressModel]  # mix pydantic model and dataclass — weird if done!


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
        [str, b"Hello%20World%21%3F", "Hello World!?"],
        [int, b"1", 1],
        [int, b"10", 10],
        [float, b"1.5", 1.5],
        [float, b"1241.5", 1241.5],
        [bool, b"1", True],
        [bool, b"0", False],
        [ExampleLiteralStr, b"Hello", "Hello"],
        [ExampleLiteralInt, b"2", 2],
    ],
)
async def test_from_header_binding(expected_type, header_value, expected_value):
    request = Request("GET", b"/", [(b"X-Foo", header_value)])

    parameter = HeaderBinder(expected_type, "X-Foo")

    value = await parameter.get_value(request)

    # the following assertion does not apply to Literal
    if expected_type not in {ExampleLiteralStr, ExampleLiteralInt}:
        assert isinstance(value, expected_type)
    assert value == expected_value


# TODO: merge with above when support for Python < 3.11 is dropped
@pytest.mark.skipif(sys.version_info < (3, 11), reason="requires python3.11 or higher")
@pytest.mark.parametrize(
    "expected_type,header_value,expected_value",
    [
        [ExampleStrEnum, b"one", ExampleStrEnum.ONE],
        [ExampleStrEnum, b"ONE", ExampleStrEnum.ONE],
        [ExampleIntEnum, b"1", ExampleIntEnum.ONE],
        [ExampleIntEnum, b"ONE", ExampleIntEnum.ONE],
    ],
)
async def test_from_header_binding_enums(expected_type, header_value, expected_value):
    await test_from_header_binding(expected_type, header_value, expected_value)


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
        [ExampleLiteralStr, b"Hello", "Hello"],
        [ExampleLiteralInt, b"2", 2],
    ],
)
async def test_from_query_binding(expected_type, query_value, expected_value):
    request = Request("GET", b"/?foo=" + query_value, None)

    parameter = QueryBinder(expected_type, "foo")

    value = await parameter.get_value(request)

    # assertion not applicable to Literal
    if expected_type not in {ExampleLiteralStr, ExampleLiteralInt}:
        assert isinstance(value, expected_type)
    assert value == expected_value


# TODO: merge with above when support for Python < 3.11 is dropped
@pytest.mark.skipif(sys.version_info < (3, 11), reason="requires python3.11 or higher")
@pytest.mark.parametrize(
    "expected_type,query_value,expected_value",
    [
        [ExampleStrEnum, b"one", ExampleStrEnum.ONE],
        [ExampleIntEnum, b"1", ExampleIntEnum.ONE],
    ],
)
async def test_from_query_binding_enums(expected_type, query_value, expected_value):
    await test_from_query_binding(expected_type, query_value, expected_value)


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

    if expected_type not in {ExampleLiteralStr, ExampleLiteralInt}:
        assert isinstance(value, expected_type)
    assert value == expected_value


# TODO: merge with above when support for Python < 3.11 is dropped
@pytest.mark.skipif(sys.version_info < (3, 11), reason="requires python3.11 or higher")
@pytest.mark.parametrize(
    "expected_type,route_value,expected_value",
    [
        [ExampleStrEnum, "one", ExampleStrEnum.ONE],
        [ExampleIntEnum, "1", ExampleIntEnum.ONE],
    ],
)
async def test_from_route_binding_enums(expected_type, route_value, expected_value):
    await test_from_route_binding(expected_type, route_value, expected_value)


@pytest.mark.parametrize("binder_type", [HeaderBinder, QueryBinder, RouteBinder])
async def test_raises_for_missing_default_converter(binder_type):
    with raises(MissingConverterError):
        binder_type("example", ExampleOne)


@pytest.mark.parametrize(
    "expected_type,invalid_value",
    [[int, "x"], [int, ""], [float, "x"], [float, ""], [bool, "x"]],
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
        [list[str], list, [b"Lorem", b"ipsum", b"dolor"], ["Lorem", "ipsum", "dolor"]],
        [
            tuple[str],
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
        [list[str], list, [b"Lorem", b"ipsum", b"dolor"], ["Lorem", "ipsum", "dolor"]],
        [
            tuple[str],
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
        [list[int], list, [b"10"], [10]],
        [list[int], list, [b"0", b"1", b"0"], [0, 1, 0]],
        [list[int], list, [b"0", b"1", b"0", b"2"], [0, 1, 0, 2]],
        [list[int], list, [b"0", b"1", b"0", b"2"], [0, 1, 0, 2]],
        [list[bytes], list, [b"0", b"1", b"0", b"2"], [b"0", b"1", b"0", b"2"]],
        [list[bool], list, [b"1"], [True]],
        [list[bool], list, [b"0", b"1", b"0"], [False, True, False]],
        [list[bool], list, [b"0", b"1", b"0", b"true"], [False, True, False, True]],
        [list[bool], list, [b"0", b"1", b"0", b"true"], [False, True, False, True]],
        [list[float], list, [b"10.2"], [10.2]],
        [list[float], list, [b"0.3", b"1", b"0"], [0.3, 1.0, 0]],
        [list[float], list, [b"0.5", b"1", b"0", b"2"], [0.5, 1.0, 0, 2.0]],
        [list[float], list, [b"0.5", b"1", b"0", b"2"], [0.5, 1.0, 0, 2.0]],
        [tuple[float], tuple, [b"10.2"], (10.2,)],
        [tuple[float], tuple, [b"0.3", b"1", b"0"], (0.3, 1.0, 0)],
        [tuple[float], tuple, [b"0.5", b"1", b"0", b"2"], (0.5, 1.0, 0, 2.0)],
        [tuple[float], tuple, [b"0.5", b"1", b"0", b"2"], (0.5, 1.0, 0, 2.0)],
        [Set[int], set, [b"10"], {10}],
        [Set[int], set, [b"0", b"1", b"0"], {0, 1, 0}],
        [Set[int], set, [b"0", b"1", b"0", b"2"], {0, 1, 0, 2}],
        [set[int], set, [b"0", b"1", b"0", b"2"], {0, 1, 0, 2}],
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
    "declared_type", [list[list[str]], tuple[tuple[str]], list[list]]
)
async def test_nested_iterables_raise_missing_converter_from_header(declared_type):
    with raises(MissingConverterError):
        HeaderBinder(declared_type)


@pytest.mark.parametrize(
    "declared_type", [list[list[str]], tuple[tuple[str]], list[list]]
)
async def test_nested_iterables_raise_missing_converter_from_query(declared_type):
    with raises(MissingConverterError):
        QueryBinder("example", declared_type)


async def test_identity_binder_identity_not_set():
    request = Request("GET", b"/", None)

    parameter = IdentityBinder(Identity)

    value = await parameter.get_value(request)

    # request.user is automatically set, if missing, to an empty object representing
    # an anonymous user
    assert value is not None


async def test_identity_binder():
    request = Request("GET", b"/", None)
    request.user = Identity()

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

        async def get_value(self, request: Request) -> str | None:
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

        async def get_value(self, request: Request) -> str | None:
            return request.method

    with pytest.raises(BinderAlreadyDefinedException):

        class MethodBinder2(Binder):
            handle = FromMethod

            async def get_value(self, request: Request) -> str | None:
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


@pytest.mark.parametrize(
    "model_class,expected_a,expected_b",
    [
        (ExampleOne, "world", 9000),  # Plain class
        (ExampleDataClass, "world", 9000),  # Dataclass
        pytest.param(
            ExamplePydanticModel,
            "world",
            9000,  # Pydantic model
            marks=pytest.mark.skipif(
                BaseModel is None, reason="pydantic not available"
            ),
        ),
    ],
)
async def test_from_body_json_binding_ignore_extra_parameters(
    model_class, expected_a, expected_b
):
    request = Request("POST", b"/", [JSONContentType]).with_content(
        JSONContent(
            {
                "a": "world",
                "b": 9000,
                "c": "This is an extra parameter that should be ignored",
            }
        )
    )

    parameter = JSONBinder(model_class)

    value = await parameter.get_value(request)

    assert isinstance(value, model_class)
    assert value.a == expected_a
    assert value.b == expected_b


@pytest.mark.parametrize("expected_type", [PlainUser, UserModel, UserDc, UserDcMix])
async def test_from_body_json_binding_ignore_extra_parameters_nested_1(expected_type):
    # Test that extra properties are ignored also in child properties
    plain_data = {
        "name": "Jane",
        "email": "jane@example.com",
        "age": 25,
        "extra_field": "ignored",
        "address": {
            "street": "456 Oak Ave",
            "city": "Seattle",
            "zip_code": "98101",
            "extra_address_field": "ignored",
        },
    }

    request = Request("POST", b"/", [JSONContentType]).with_content(
        JSONContent(plain_data)
    )

    parameter = JSONBinder(expected_type)

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value.name == "Jane"
    assert value.address.street == "456 Oak Ave"


@pytest.mark.parametrize("expected_type", [PlainUser2, UserModel2, UserDc2, UserDc2Mix])
async def test_from_body_json_binding_ignore_extra_parameters_nested_2(expected_type):
    # Test that extra properties are ignored also in child properties
    plain_data = {
        "name": "Jane",
        "email": "jane@example.com",
        "age": 25,
        "extra_field": "ignored",
        "addresses": [
            {
                "street": "456 Oak Ave",
                "city": "Seattle",
                "zip_code": "98101",
                "extra_address_field": "ignored",
            },
            {
                "street": "Foo",
                "city": "Foo City",
                "zip_code": "00888",
                "extra_address_field": "ignored",
                "some_other_field": 3,
            },
        ],
    }

    request = Request("POST", b"/", [JSONContentType]).with_content(
        JSONContent(plain_data)
    )

    parameter = JSONBinder(expected_type)

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value.name == "Jane"
    assert value.addresses[0].street == "456 Oak Ave"
    assert value.addresses[1].street == "Foo"


@pytest.mark.parametrize(
    "collection_type,model_class,expected_type",
    [
        (list[ExampleOne], ExampleOne, list),
        (list[ExampleDataClass], ExampleDataClass, list),
        pytest.param(
            list[ExamplePydanticModel],
            ExamplePydanticModel,
            list,
            marks=pytest.mark.skipif(
                BaseModel is None, reason="pydantic not available"
            ),
        ),
        (Sequence[ExampleOne], ExampleOne, list),
        (Sequence[ExampleDataClass], ExampleDataClass, list),
        pytest.param(
            Sequence[ExamplePydanticModel],
            ExamplePydanticModel,
            list,
            marks=pytest.mark.skipif(
                BaseModel is None, reason="pydantic not available"
            ),
        ),
    ],
)
async def test_from_body_json_binding_collections(
    collection_type, model_class, expected_type
):
    request = Request("POST", b"/", [JSONContentType]).with_content(
        JSONContent(
            [
                {"a": "first", "b": 100, "c": "extra property to ignore 1"},
                {"a": "second", "b": 200, "c": "extra property to ignore 2"},
                {"a": "third", "b": 300, "c": "extra property to ignore 3"},
            ]
        )
    )

    parameter = JSONBinder(collection_type)

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert len(value) == 3

    # Convert to list for uniform iteration (since sets don't guarantee order)
    items = list(value)

    for i, item in enumerate(items):
        assert isinstance(item, model_class)
        # For sets, we can't guarantee order, so we check that all expected values are present
        if expected_type == set:
            assert item.a in ["first", "second", "third"]
            assert item.b in [100, 200, 300]
        else:
            # For lists and sequences, order is preserved
            expected_values = [("first", 100), ("second", 200), ("third", 300)]
            assert item.a == expected_values[i][0]
            assert item.b == expected_values[i][1]


@pytest.mark.parametrize(
    "expected_type",
    [
        PlainUserWithContactsUUID,
        UserModelWithContactsUUID,
        UserDcWithContactsUUID,
    ],
)
async def test_from_body_json_binding_dict_uuid_custom_class(expected_type):
    """Test conversion of dict[UUID, CustomClass] from JSON body"""
    uuid_home = "b0c1f822-b63c-475e-9f2e-b6406bafcc2b"
    uuid_work = "d5fd0cde-4ad6-4b61-a5b1-5b8e6d48cebe"
    uuid_mobile = "00000000-0000-0000-0000-000000000000"

    data = {
        "name": "Jane",
        "email": "jane@example.com",
        "age": 25,
        "contacts": {
            uuid_home: {
                "phone": "555-1234",
                "email": "jane.home@example.com",
                "created_at": "2023-01-15T10:30:00",
                "extra_field": "should be ignored",
            },
            uuid_work: {
                "phone": "555-5678",
                "email": "jane.work@example.com",
                "created_at": "2023-02-20T14:45:00",
                "extra_field": "should be ignored",
            },
            uuid_mobile: {
                "phone": "555-9999",
                "email": "jane.mobile@example.com",
                "created_at": "2023-03-25T08:15:00",
                "extra_field": "should be ignored",
            },
        },
    }

    request = Request("POST", b"/", [JSONContentType]).with_content(JSONContent(data))

    parameter = JSONBinder(expected_type)

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value.name == "Jane"
    assert value.email == "jane@example.com"
    assert value.age == 25
    assert isinstance(value.contacts, dict)
    assert len(value.contacts) == 3

    # Check that keys are UUIDs
    for key in value.contacts.keys():
        assert isinstance(key, UUID)

    # Check specific values
    assert UUID(uuid_home) in value.contacts
    assert UUID(uuid_work) in value.contacts
    assert UUID(uuid_mobile) in value.contacts
    assert value.contacts[UUID(uuid_home)].phone == "555-1234"
    assert value.contacts[UUID(uuid_home)].email == "jane.home@example.com"
    assert value.contacts[UUID(uuid_home)].created_at == datetime(
        2023, 1, 15, 10, 30, 0
    )
    assert value.contacts[UUID(uuid_work)].phone == "555-5678"
    assert value.contacts[UUID(uuid_work)].email == "jane.work@example.com"
    assert value.contacts[UUID(uuid_work)].created_at == datetime(
        2023, 2, 20, 14, 45, 0
    )
    assert value.contacts[UUID(uuid_mobile)].created_at == datetime(
        2023, 3, 25, 8, 15, 0
    )


@pytest.mark.parametrize(
    "expected_type",
    [
        PlainUserWithContacts,
        UserModelWithContacts,
        UserDcWithContacts,
    ],
)
async def test_from_body_json_binding_dict_str_custom_class(expected_type):
    """Test conversion of dict[str, CustomClass] from JSON body"""
    data = {
        "name": "Jane",
        "email": "jane@example.com",
        "age": 25,
        "contacts": {
            "home": {
                "phone": "555-1234",
                "email": "jane.home@example.com",
                "created_at": "2023-01-15T10:30:00",
            },
            "work": {
                "phone": "555-5678",
                "email": "jane.work@example.com",
                "created_at": "2023-02-20T14:45:00",
            },
            "mobile": {
                "phone": "555-9999",
                "email": "jane.mobile@example.com",
                "created_at": "2023-03-25T08:15:00",
            },
        },
    }

    request = Request("POST", b"/", [JSONContentType]).with_content(JSONContent(data))

    parameter = JSONBinder(expected_type)

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value.name == "Jane"
    assert value.email == "jane@example.com"
    assert value.age == 25
    assert isinstance(value.contacts, dict)
    assert len(value.contacts) == 3
    assert "home" in value.contacts
    assert "work" in value.contacts
    assert "mobile" in value.contacts
    assert value.contacts["home"].phone == "555-1234"
    assert value.contacts["home"].email == "jane.home@example.com"
    assert value.contacts["home"].created_at == datetime(2023, 1, 15, 10, 30, 0)
    assert value.contacts["work"].phone == "555-5678"
    assert value.contacts["work"].email == "jane.work@example.com"
    assert value.contacts["work"].created_at == datetime(2023, 2, 20, 14, 45, 0)


@pytest.mark.parametrize(
    "expected_type",
    [
        PlainUserWithContactsUUID,
        UserModelWithContactsUUID,
        UserDcWithContactsUUID,
    ],
)
async def test_from_body_json_binding_empty_dict(expected_type):
    """Test conversion with empty dict"""
    data = {
        "name": "Jane",
        "email": "jane@example.com",
        "age": 25,
        "contacts": {},
    }

    request = Request("POST", b"/", [JSONContentType]).with_content(JSONContent(data))

    parameter = JSONBinder(expected_type)

    value = await parameter.get_value(request)

    assert isinstance(value, expected_type)
    assert value.name == "Jane"
    assert value.email == "jane@example.com"
    assert value.age == 25
    assert isinstance(value.contacts, dict)
    assert len(value.contacts) == 0


# region MultiFormatBodyBinder tests

from blacksheep.exceptions import UnsupportedMediaType as UnsupportedMediaTypeExc
from blacksheep.server.bindings import FormBinder, MultiFormatBodyBinder


@dataclass
class MultiItem:
    name: str
    value: int


async def test_multi_format_binder_dispatches_to_json():
    binder = MultiFormatBodyBinder(
        [JSONBinder(MultiItem, "body", False, True), FormBinder(MultiItem, "body", False, True)],
        MultiItem,
        "body",
        required=True,
    )
    request = Request(
        "POST", b"/", [(b"content-type", b"application/json")]
    ).with_content(JSONContent({"name": "test", "value": 42}))

    result = await binder.get_value(request)
    assert isinstance(result, MultiItem)
    assert result.name == "test"
    assert result.value == 42


async def test_multi_format_binder_dispatches_to_form():
    binder = MultiFormatBodyBinder(
        [JSONBinder(MultiItem, "body", False, True), FormBinder(MultiItem, "body", False, True)],
        MultiItem,
        "body",
        required=True,
    )
    request = Request(
        "POST", b"/", [(b"content-type", b"application/x-www-form-urlencoded")]
    ).with_content(FormContent({"name": "test", "value": "42"}))

    result = await binder.get_value(request)
    assert isinstance(result, MultiItem)
    assert result.name == "test"


async def test_multi_format_binder_raises_415_for_unsupported_content_type():
    binder = MultiFormatBodyBinder(
        [JSONBinder(MultiItem, "body", False, True), FormBinder(MultiItem, "body", False, True)],
        MultiItem,
        "body",
        required=True,
    )
    from blacksheep.contents import Content

    request = Request(
        "POST", b"/", [(b"content-type", b"application/xml")]
    ).with_content(Content(b"application/xml", b"<MultiItem/>"))

    with pytest.raises(UnsupportedMediaTypeExc):
        await binder.get_value(request)


async def test_multi_format_binder_returns_none_when_optional_and_no_match():
    binder = MultiFormatBodyBinder(
        [JSONBinder(MultiItem, "body", False, False), FormBinder(MultiItem, "body", False, False)],
        MultiItem,
        "body",
        required=False,
    )
    from blacksheep.contents import Content

    request = Request(
        "POST", b"/", [(b"content-type", b"application/xml")]
    ).with_content(Content(b"application/xml", b"<MultiItem/>"))

    result = await binder.get_value(request)
    assert result is None


async def test_multi_format_binder_skips_excluded_methods():
    binder = MultiFormatBodyBinder(
        [JSONBinder(dict, "body", False, False)],
        dict,
        "body",
        required=False,
    )
    for method in ("GET", "HEAD", "TRACE"):
        request = Request(
            method, b"/", [(b"content-type", b"application/json")]
        ).with_content(JSONContent({"x": 1}))
        result = await binder.get_value(request)
        assert result is None


def test_multi_format_binder_content_type_combines_inner():
    binder = MultiFormatBodyBinder(
        [JSONBinder(dict, "body"), FormBinder(dict, "body")],
        dict,
        "body",
    )
    parts = binder.content_type.split(";")
    assert "application/json" in parts
    assert "multipart/form-data" in parts
    assert "application/x-www-form-urlencoded" in parts


# endregion


# region XMLBinder tests

from blacksheep.contents import Content
from blacksheep.server.bindings import FromXML, XMLBinder


XML_ITEM = b"<Item><name>hello</name><value>7</value></Item>"
XML_NESTED = b"<Root><inner><x>1</x></inner></Root>"
XML_ATTR = b'<Item id="99"><name>attr</name></Item>'
XML_LIST = b"<Items><tag>a</tag><tag>b</tag></Items>"


async def test_xml_binder_parses_simple_fields():
    binder = XMLBinder(MultiItem, "body", required=True)
    request = Request(
        "POST", b"/", [(b"content-type", b"application/xml")]
    ).with_content(Content(b"application/xml", XML_ITEM))

    result = await binder.get_value(request)
    assert isinstance(result, MultiItem)
    assert result.name == "hello"
    assert result.value == 7  # coerced from string


async def test_xml_binder_accepts_text_xml_content_type():
    binder = XMLBinder(MultiItem, "body", required=True)
    request = Request(
        "POST", b"/", [(b"content-type", b"text/xml")]
    ).with_content(Content(b"text/xml", XML_ITEM))

    result = await binder.get_value(request)
    assert isinstance(result, MultiItem)


async def test_xml_binder_does_not_match_json_content_type():
    binder = XMLBinder(MultiItem, "body", required=False)
    request = Request(
        "POST", b"/", [(b"content-type", b"application/json")]
    ).with_content(JSONContent({"name": "x", "value": 1}))

    result = await binder.get_value(request)
    assert result is None


async def test_xml_binder_raises_bad_request_for_malformed_xml():
    binder = XMLBinder(dict, "body", required=True)
    request = Request(
        "POST", b"/", [(b"content-type", b"application/xml")]
    ).with_content(Content(b"application/xml", b"<unclosed"))

    with pytest.raises(InvalidRequestBody):
        await binder.get_value(request)


async def test_xml_binder_raises_missing_body_for_empty_content():
    binder = XMLBinder(dict, "body", required=True)
    # required=True and content-type matches, so empty body → MissingBodyError
    request = Request("POST", b"/", [(b"content-type", b"application/xml")])

    with pytest.raises(MissingBodyError):
        await binder.get_value(request)


def test_xml_binder_rejects_xxe_attack():
    """Verify defusedxml blocks external entity injection."""
    import defusedxml

    xxe_payload = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        b"<Item><name>&xxe;</name><value>1</value></Item>"
    )
    with pytest.raises(
        (defusedxml.DTDForbidden, defusedxml.EntitiesForbidden, defusedxml.ExternalReferenceForbidden)
    ):
        XMLBinder._parse_xml(xxe_payload)


def test_xml_binder_rejects_billion_laughs():
    """Verify defusedxml blocks entity expansion (billion laughs)."""
    import defusedxml

    billion_laughs = (
        b'<?xml version="1.0"?>'
        b"<!DOCTYPE lolz ["
        b'  <!ENTITY lol "lol">'
        b'  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        b"]>"
        b"<Item><name>&lol2;</name><value>1</value></Item>"
    )
    with pytest.raises((defusedxml.DTDForbidden, defusedxml.EntitiesForbidden)):
        XMLBinder._parse_xml(billion_laughs)


def test_element_to_dict_handles_attributes():
    from blacksheep.server.bindings import _element_to_dict
    import xml.etree.ElementTree as ET

    root = ET.fromstring(XML_ATTR)
    d = _element_to_dict(root)
    assert d["id"] == "99"
    assert d["name"] == "attr"


def test_element_to_dict_handles_nested():
    from blacksheep.server.bindings import _element_to_dict
    import xml.etree.ElementTree as ET

    root = ET.fromstring(XML_NESTED)
    d = _element_to_dict(root)
    assert isinstance(d["inner"], dict)
    assert d["inner"]["x"] == "1"


def test_element_to_dict_collects_repeated_tags_as_list():
    from blacksheep.server.bindings import _element_to_dict
    import xml.etree.ElementTree as ET

    root = ET.fromstring(XML_LIST)
    d = _element_to_dict(root)
    assert d["tag"] == ["a", "b"]


def test_xml_binder_content_type():
    binder = XMLBinder(dict, "body")
    parts = binder.content_type.split(";")
    assert "application/xml" in parts
    assert "text/xml" in parts


# endregion
