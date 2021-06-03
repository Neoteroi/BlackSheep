from dataclasses import dataclass
from enum import IntEnum
from typing import ForwardRef, Generic, List, Optional, TypeVar, Union

import pytest
from blacksheep.server.application import Application
from blacksheep.server.openapi.common import (
    ContentInfo,
    OpenAPIEndpointException,
    ResponseInfo,
)
from blacksheep.server.openapi.exceptions import (
    DuplicatedContentTypeDocsException,
    UnsupportedUnionTypeException,
)
from blacksheep.server.openapi.v3 import OpenAPIHandler, check_union
from openapidocs.common import Format
from openapidocs.v3 import Info, Reference, Schema, ValueType

T = TypeVar("T")


@dataclass
class PaginatedSet(Generic[T]):
    items: List[T]
    total: int


@dataclass
class Validated(Generic[T]):
    data: T
    error: str


@dataclass
class SubValidated(Generic[T]):
    sub: Validated[T]


class FooLevel(IntEnum):
    BASIC = 1
    MEDIUM = 2
    SUPER = 3


@dataclass
class Foo:
    a: str
    b: bool
    level: Optional[FooLevel] = None


@dataclass
class Ufo:
    b: bool
    c: str


@pytest.mark.asyncio
async def test_raises_for_started_app():
    app = Application()

    await app.start()

    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))

    with pytest.raises(TypeError):
        docs.bind_app(app)


@pytest.mark.asyncio
async def test_raises_for_duplicated_content_example():
    app = Application()

    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))

    @app.router.get("/")
    @docs(
        responses={
            200: ResponseInfo("Example", content=[ContentInfo(Foo), ContentInfo(Foo)])
        }
    )
    async def example():
        ...

    with pytest.raises(DuplicatedContentTypeDocsException):
        docs.bind_app(app)
        await app.start()


@pytest.mark.asyncio
def test_raises_for_union_type():
    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))
    with pytest.raises(UnsupportedUnionTypeException):
        docs.get_schema_by_type(Union[Foo, Ufo])


@pytest.mark.parametrize(
    "annotation,expected_result",
    [
        (Foo, [False, Foo]),
        (Optional[Foo], [True, Foo]),
        (Union[Foo, None], [True, Foo]),
        (Union[None, Foo], [True, Foo]),
    ],
)
def test_check_union(annotation, expected_result):
    assert check_union(annotation) == tuple(expected_result)


def test_register_schema_can_handle_classes_with_same_name():
    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))

    @dataclass
    class FooX:
        x: str

    FooX.__name__ = "Foo"

    docs.register_schema_for_type(Foo)
    docs.register_schema_for_type(FooX)

    foo_schema = docs.components.schemas["Foo"]
    foox_schema = docs.components.schemas["Foo1"]

    assert foo_schema is not None
    assert foox_schema is not None

    assert isinstance(foo_schema, Schema)
    assert isinstance(foox_schema, Schema)

    assert "x" in foox_schema.properties
    assert "a" in foo_schema.properties


def test_register_schema_handles_repeated_calls():
    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))

    docs.register_schema_for_type(Foo)
    docs.register_schema_for_type(Foo)
    docs.register_schema_for_type(Foo)

    assert docs.components.schemas is not None
    assert len(docs.components.schemas) == 1
    foo_schema = docs.components.schemas["Foo"]
    assert "Foo1" not in docs.components.schemas

    assert foo_schema is not None
    assert isinstance(foo_schema, Schema)
    assert "a" in foo_schema.properties


def test_handles_forward_refs():
    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))

    @dataclass
    class Friend:
        foo: "Foo"

    docs.register_schema_for_type(Foo)
    docs.register_schema_for_type(Friend)

    assert docs.components.schemas is not None
    assert len(docs.components.schemas) == 2
    friend_schema = docs.components.schemas["Friend"]

    assert friend_schema is not None
    assert isinstance(friend_schema, Schema)
    assert friend_schema.properties["foo"] == Reference(ref="#/components/schemas/Foo")


def test_register_schema_for_enum():
    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))

    docs.register_schema_for_type(FooLevel)

    assert docs.components.schemas is not None
    assert len(docs.components.schemas) == 1
    schema = docs.components.schemas["FooLevel"]

    assert isinstance(schema, Schema)

    assert schema is not None
    assert schema.type == ValueType.INTEGER
    assert schema.enum == [x.value for x in FooLevel]


def test_try_get_schema_for_enum_returns_none_for_not_enum():
    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))

    assert docs._try_get_schema_for_enum(Foo) is None


def test_get_parameters_returns_non_for_object_without_binders():
    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))
    assert docs.get_parameters(Foo) is None
    assert docs.get_request_body(Foo) is None


def test_get_content_from_response_info_returns_none_for_missing_content():
    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))
    assert docs._get_content_from_response_info(None) is None


def test_get_schema_by_type_returns_reference_for_forward_ref():
    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))
    assert docs._get_schema_by_type(ForwardRef("Foo")) == Reference(
        "#/components/schemas/Foo"
    )


@pytest.mark.parametrize(
    "json_path,yaml_path,preferred_format,expected_result",
    [
        ["foo.json", "foo.yaml", Format.YAML, "foo.yaml"],
        ["foo.json", "foo.yaml", Format.JSON, "foo.json"],
        ["/openapi.json", "/openapi.yaml", Format.YAML, "/openapi.yaml"],
    ],
)
def test_get_spec_path_preferred_format(
    json_path, yaml_path, preferred_format, expected_result
):
    docs = OpenAPIHandler(
        info=Info("Example", "0.0.1"),
        json_spec_path=json_path,
        yaml_spec_path=yaml_path,
        preferred_format=preferred_format,
    )

    assert docs.get_spec_path() == expected_result


def test_get_spec_path_raises_for_unsupported_preferred_format():
    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))
    docs.preferred_format = "NOPE"  # type: ignore

    with pytest.raises(OpenAPIEndpointException):
        docs.get_spec_path()


def test_register_schema_for_generic_with_list():
    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))

    docs.register_schema_for_type(PaginatedSet[Foo])

    assert docs.components.schemas is not None
    schema = docs.components.schemas["PaginatedSet<Foo>"]

    assert isinstance(schema, Schema)

    assert schema is not None


def test_register_schema_for_multiple_generic_with_list():
    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))

    docs.register_schema_for_type(PaginatedSet[Foo])
    docs.register_schema_for_type(PaginatedSet[Ufo])

    assert docs.components.schemas is not None
    schema = docs.components.schemas["PaginatedSet<Foo>"]
    assert isinstance(schema, Schema)

    schema = docs.components.schemas["PaginatedSet<Ufo>"]
    assert isinstance(schema, Schema)

    assert schema is not None


def test_register_schema_for_generic_with_property():
    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))

    docs.register_schema_for_type(Validated[Foo])

    assert docs.components.schemas is not None
    schema = docs.components.schemas["Validated<Foo>"]

    assert isinstance(schema, Schema)

    assert schema is not None


def test_register_schema_for_generic_sub_property():
    docs = OpenAPIHandler(info=Info("Example", "0.0.1"))

    docs.register_schema_for_type(Validated[Foo])
    docs.register_schema_for_type(SubValidated[Foo])

    assert docs.components.schemas is not None
    schema = docs.components.schemas["SubValidated<Foo>"]

    assert isinstance(schema, Schema)

    assert schema is not None
