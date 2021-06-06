from blacksheep.server.routing import RoutesRegistry
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
from openapidocs.common import Format, Serializer
from openapidocs.v3 import Info, Reference, Schema, ValueType

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class Cat:
    id: int
    name: str


@dataclass
class Combo(Generic[T, U]):
    item_one: T
    item_two: U


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


@pytest.fixture
def app() -> Application:
    app = Application()
    app.controllers_router = RoutesRegistry()
    return app


@pytest.fixture
def docs() -> OpenAPIHandler:
    # example documentation
    return OpenAPIHandler(info=Info("Example", "0.0.1"))


@pytest.fixture
def serializer() -> Serializer:
    return Serializer()


@pytest.mark.asyncio
async def test_raises_for_started_app(docs):
    app = Application()

    await app.start()

    with pytest.raises(TypeError):
        docs.bind_app(app)


@pytest.mark.asyncio
async def test_raises_for_duplicated_content_example(docs, app):
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
def test_raises_for_union_type(docs):
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


def test_register_schema_can_handle_classes_with_same_name(docs):
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


def test_register_schema_handles_repeated_calls(docs):
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


def test_handles_forward_refs(docs):
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


def test_register_schema_for_enum(docs):
    docs.register_schema_for_type(FooLevel)

    assert docs.components.schemas is not None
    assert len(docs.components.schemas) == 1
    schema = docs.components.schemas["FooLevel"]

    assert isinstance(schema, Schema)

    assert schema is not None
    assert schema.type == ValueType.INTEGER
    assert schema.enum == [x.value for x in FooLevel]


def test_try_get_schema_for_enum_returns_none_for_not_enum(docs):
    assert docs._try_get_schema_for_enum(Foo) is None


def test_get_parameters_returns_non_for_object_without_binders(docs):
    assert docs.get_parameters(Foo) is None
    assert docs.get_request_body(Foo) is None


def test_get_content_from_response_info_returns_none_for_missing_content(docs):
    assert docs._get_content_from_response_info(None) is None


def test_get_schema_by_type_returns_reference_for_forward_ref(docs):
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


def test_get_spec_path_raises_for_unsupported_preferred_format(docs):
    docs.preferred_format = "NOPE"  # type: ignore

    with pytest.raises(OpenAPIEndpointException):
        docs.get_spec_path()


def test_register_schema_for_generic_with_list(
    docs: OpenAPIHandler, serializer: Serializer
):
    docs.register_schema_for_type(PaginatedSet[Foo])

    assert docs.components.schemas is not None
    schema = docs.components.schemas["PaginatedSet<Foo>"]

    assert isinstance(schema, Schema)

    yaml = serializer.to_yaml(docs.generate_documentation(Application()))

    assert (
        yaml.strip()
        == """
openapi: 3.0.3
info:
    title: Example
    version: 0.0.1
paths: {}
components:
    schemas:
        Foo:
            type: object
            required:
            - a
            - b
            properties:
                a:
                    type: string
                    nullable: false
                b:
                    type: boolean
                    nullable: false
                level:
                    type: integer
                    nullable: false
                    enum:
                    - 1
                    - 2
                    - 3
        PaginatedSet<Foo>:
            type: object
            required:
            - items
            - total
            properties:
                items:
                    type: array
                    nullable: false
                    items:
                        $ref: '#/components/schemas/Foo'
                total:
                    type: integer
                    format: int64
                    nullable: false
""".strip()
    )


def test_register_schema_for_multiple_generic_with_list(
    docs: OpenAPIHandler, serializer: Serializer
):
    docs.register_schema_for_type(PaginatedSet[Foo])
    docs.register_schema_for_type(PaginatedSet[Ufo])

    assert docs.components.schemas is not None
    schema = docs.components.schemas["PaginatedSet<Foo>"]
    assert isinstance(schema, Schema)

    schema = docs.components.schemas["PaginatedSet<Ufo>"]
    assert isinstance(schema, Schema)

    yaml = serializer.to_yaml(docs.generate_documentation(Application()))

    assert (
        yaml.strip()
        == """
openapi: 3.0.3
info:
    title: Example
    version: 0.0.1
paths: {}
components:
    schemas:
        Foo:
            type: object
            required:
            - a
            - b
            properties:
                a:
                    type: string
                    nullable: false
                b:
                    type: boolean
                    nullable: false
                level:
                    type: integer
                    nullable: false
                    enum:
                    - 1
                    - 2
                    - 3
        PaginatedSet<Foo>:
            type: object
            required:
            - items
            - total
            properties:
                items:
                    type: array
                    nullable: false
                    items:
                        $ref: '#/components/schemas/Foo'
                total:
                    type: integer
                    format: int64
                    nullable: false
        Ufo:
            type: object
            required:
            - b
            - c
            properties:
                b:
                    type: boolean
                    nullable: false
                c:
                    type: string
                    nullable: false
        PaginatedSet<Ufo>:
            type: object
            required:
            - items
            - total
            properties:
                items:
                    type: array
                    nullable: false
                    items:
                        $ref: '#/components/schemas/Ufo'
                total:
                    type: integer
                    format: int64
                    nullable: false
""".strip()
    )


def test_register_schema_for_generic_with_property(
    docs: OpenAPIHandler, serializer: Serializer
):
    docs.register_schema_for_type(Validated[Foo])

    assert docs.components.schemas is not None
    schema = docs.components.schemas["Validated<Foo>"]

    assert isinstance(schema, Schema)

    yaml = serializer.to_yaml(docs.generate_documentation(Application()))

    assert (
        yaml.strip()
        == """
openapi: 3.0.3
info:
    title: Example
    version: 0.0.1
paths: {}
components:
    schemas:
        Foo:
            type: object
            required:
            - a
            - b
            properties:
                a:
                    type: string
                    nullable: false
                b:
                    type: boolean
                    nullable: false
                level:
                    type: integer
                    nullable: false
                    enum:
                    - 1
                    - 2
                    - 3
        Validated<Foo>:
            type: object
            required:
            - data
            - error
            properties:
                data:
                    $ref: '#/components/schemas/Foo'
                error:
                    type: string
                    nullable: false
""".strip()
    )


def test_register_schema_for_generic_sub_property(
    docs: OpenAPIHandler, serializer: Serializer
):
    docs.register_schema_for_type(Validated[Foo])
    docs.register_schema_for_type(SubValidated[Foo])

    assert docs.components.schemas is not None
    schema = docs.components.schemas["SubValidated<Foo>"]

    assert isinstance(schema, Schema)

    yaml = serializer.to_yaml(docs.generate_documentation(Application()))

    assert (
        yaml.strip()
        == """
openapi: 3.0.3
info:
    title: Example
    version: 0.0.1
paths: {}
components:
    schemas:
        Foo:
            type: object
            required:
            - a
            - b
            properties:
                a:
                    type: string
                    nullable: false
                b:
                    type: boolean
                    nullable: false
                level:
                    type: integer
                    nullable: false
                    enum:
                    - 1
                    - 2
                    - 3
        Validated<Foo>:
            type: object
            required:
            - data
            - error
            properties:
                data:
                    $ref: '#/components/schemas/Foo'
                error:
                    type: string
                    nullable: false
        SubValidated<Foo>:
            type: object
            required:
            - sub
            properties:
                sub:
                    $ref: '#/components/schemas/Validated<Foo>'
""".strip()
    )


@pytest.mark.asyncio
async def test_register_schema_for_multi_generic(
    app: Application, docs: OpenAPIHandler, serializer: Serializer
):
    @app.route("/combo")
    def combo_example() -> Combo[Cat, Foo]:
        ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    assert (
        yaml.strip()
        == """
openapi: 3.0.3
info:
    title: Example
    version: 0.0.1
paths:
    /combo:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/Combo<Cat, Foo>'
            operationId: combo_example
components:
    schemas:
        Cat:
            type: object
            required:
            - id
            - name
            properties:
                id:
                    type: integer
                    format: int64
                    nullable: false
                name:
                    type: string
                    nullable: false
        Foo:
            type: object
            required:
            - a
            - b
            properties:
                a:
                    type: string
                    nullable: false
                b:
                    type: boolean
                    nullable: false
                level:
                    type: integer
                    nullable: false
                    enum:
                    - 1
                    - 2
                    - 3
        Combo<Cat, Foo>:
            type: object
            required:
            - item_one
            - item_two
            properties:
                item_one:
                    $ref: '#/components/schemas/Cat'
                item_two:
                    $ref: '#/components/schemas/Foo'
""".strip()
    )
