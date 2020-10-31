from dataclasses import dataclass
from enum import IntEnum
from typing import ForwardRef, Optional, Union

import pytest
from blacksheep.server.application import Application
from blacksheep.server.openapi.common import ContentInfo, ResponseInfo
from blacksheep.server.openapi.exceptions import (
    DuplicatedContentTypeDocsException,
    UnsupportedUnionTypeException,
)
from blacksheep.server.openapi.v3 import OpenAPIHandler, check_union
from openapidocs.v3 import Info, Reference, Schema, ValueType


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
