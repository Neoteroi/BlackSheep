from dataclasses import dataclass
from enum import IntEnum
from typing import Generic, List, Optional, Sequence, TypeVar, Union

import pytest
from blacksheep.server.application import Application
from blacksheep.server.openapi.common import (
    ContentInfo,
    EndpointDocs,
    OpenAPIEndpointException,
    ResponseInfo,
)
from blacksheep.server.openapi.exceptions import (
    DuplicatedContentTypeDocsException,
    UnsupportedUnionTypeException,
)
from blacksheep.server.openapi.v3 import (
    DataClassTypeHandler,
    OpenAPIHandler,
    PydanticModelTypeHandler,
    check_union,
)
from blacksheep.server.routing import RoutesRegistry
from openapidocs.common import Format, Serializer
from openapidocs.v3 import Info, Reference, Schema, ValueType
from pydantic import BaseModel

T = TypeVar("T")
U = TypeVar("U")


class PydCat(BaseModel):
    id: int
    name: str


class PydPaginatedSet(BaseModel, Generic[T]):
    items: List[T]
    total: int


class PlainClass:
    id: int
    name: str


@dataclass
class Cat:
    id: int
    name: str


@dataclass
class CreateCatInput:
    name: str


@dataclass
class CatOwner:
    id: int
    first_name: str
    last_name: str


@dataclass
class CatDetails(Cat):
    owner: CatOwner
    friends: List[int]


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


@dataclass
class ForwardRefExample:
    value: "PaginatedSet[Cat]"


@dataclass
class GenericWithForwardRefExample(Generic[T]):
    ufo: "Ufo"
    value: "PaginatedSet[T]"


def get_app() -> Application:
    app = Application()
    app.controllers_router = RoutesRegistry()
    return app


def get_cats_api() -> Application:
    app = Application()
    app.controllers_router = RoutesRegistry()
    get = app.router.get
    post = app.router.post
    delete = app.router.delete

    @get("/api/cats")
    def get_cats() -> PaginatedSet[Cat]:
        ...

    @get("/api/cats/{cat_id}")
    def get_cat_details(cat_id: int) -> CatDetails:
        ...

    @post("/api/cats")
    def create_cat(input: CreateCatInput) -> Cat:
        ...

    @delete("/api/cats/{cat_id}")
    def delete_cat(cat_id: int) -> None:
        ...

    return app


@pytest.fixture(scope="function")
def docs() -> OpenAPIHandler:
    # example documentation
    return OpenAPIHandler(info=Info("Example", "0.0.1"))


class CapitalizeOperationDocs(OpenAPIHandler):
    def get_operation_id(self, docs: Optional[EndpointDocs], handler) -> str:
        return handler.__name__.capitalize().replace("_", " ")


@pytest.fixture
def capitalize_operation_id_docs() -> CapitalizeOperationDocs:
    return CapitalizeOperationDocs(info=Info("Example", "0.0.1"))


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
async def test_raises_for_duplicated_content_example(docs):
    app = get_app()

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


def test_open_api_handler_object_handlers(docs: OpenAPIHandler):
    assert docs.object_types_handlers is not None
    assert isinstance(docs.object_types_handlers[0], DataClassTypeHandler)
    assert isinstance(docs.object_types_handlers[1], PydanticModelTypeHandler)


def test_open_api_handler_get_fields(docs: OpenAPIHandler):
    assert docs.get_fields(None) == []


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
    schema = docs.components.schemas["PaginatedSetOfFoo"]

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
        PaginatedSetOfFoo:
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
    schema = docs.components.schemas["PaginatedSetOfFoo"]
    assert isinstance(schema, Schema)

    schema = docs.components.schemas["PaginatedSetOfUfo"]
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
        PaginatedSetOfFoo:
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
        PaginatedSetOfUfo:
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
    schema = docs.components.schemas["ValidatedOfFoo"]

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
        ValidatedOfFoo:
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
    schema = docs.components.schemas["SubValidatedOfFoo"]

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
        ValidatedOfFoo:
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
        SubValidatedOfFoo:
            type: object
            required:
            - sub
            properties:
                sub:
                    $ref: '#/components/schemas/ValidatedOfFoo'
""".strip()
    )


@pytest.mark.asyncio
async def test_register_schema_for_multi_generic(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

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
                                $ref: '#/components/schemas/ComboOfCatAndFoo'
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
        ComboOfCatAndFoo:
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


@pytest.mark.asyncio
async def test_register_schema_for_generic_with_list_reusing_ref(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.route("/one")
    def one() -> PaginatedSet[Cat]:
        ...

    @app.route("/two")
    def two() -> PaginatedSet[Cat]:
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
    /one:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/PaginatedSetOfCat'
            operationId: one
    /two:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/PaginatedSetOfCat'
            operationId: two
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
        PaginatedSetOfCat:
            type: object
            required:
            - items
            - total
            properties:
                items:
                    type: array
                    nullable: false
                    items:
                        $ref: '#/components/schemas/Cat'
                total:
                    type: integer
                    format: int64
                    nullable: false
""".strip()
    )


def test_get_type_name_raises_for_invalid_object_type(docs: OpenAPIHandler):
    with pytest.raises(ValueError):
        docs.get_type_name(10)


@pytest.mark.asyncio
async def test_handling_of_forward_references(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.route("/")
    def forward_ref_example() -> ForwardRefExample:
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
    /:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/ForwardRefExample'
            operationId: forward_ref_example
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
        PaginatedSetOfCat:
            type: object
            required:
            - items
            - total
            properties:
                items:
                    type: array
                    nullable: false
                    items:
                        $ref: '#/components/schemas/Cat'
                total:
                    type: integer
                    format: int64
                    nullable: false
        ForwardRefExample:
            type: object
            required:
            - value
            properties:
                value:
                    $ref: '#/components/schemas/PaginatedSetOfCat'
""".strip()
    )


@pytest.mark.asyncio
async def test_handling_of_normal_class(docs: OpenAPIHandler, serializer: Serializer):
    """
    Plain classes are simply ignored, since their handling would be ambiguous:
    should the library inspect type annotations, __dict__?
    (in fact, the built-in json module throws for them).
    """
    app = get_app()

    @app.route("/")
    def plain_class() -> PlainClass:
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
    /:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                nullable: false
            operationId: plain_class
components: {}
""".strip()
    )


@pytest.mark.asyncio
async def test_handling_of_pydantic_generic_class(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.route("/")
    def home() -> PydPaginatedSet[Cat]:
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
    /:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/PydPaginatedSetOfCat'
            operationId: home
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
        PydPaginatedSetOfCat:
            type: object
            required:
            - items
            - total
            properties:
                items:
                    type: array
                    nullable: false
                    items:
                        $ref: '#/components/schemas/Cat'
                total:
                    type: integer
                    format: int64
                    nullable: false
""".strip()
    )


@pytest.mark.asyncio
async def test_handling_of_pydantic_class_in_generic(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.route("/")
    def home() -> PaginatedSet[PydCat]:
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
    /:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/PaginatedSetOfPydCat'
            operationId: home
components:
    schemas:
        PydCat:
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
        PaginatedSetOfPydCat:
            type: object
            required:
            - items
            - total
            properties:
                items:
                    type: array
                    nullable: false
                    items:
                        $ref: '#/components/schemas/PydCat'
                total:
                    type: integer
                    format: int64
                    nullable: false
""".strip()
    )


@pytest.mark.asyncio
async def test_handling_of_sequence(docs: OpenAPIHandler, serializer: Serializer):
    app = get_app()

    @app.route("/")
    def home() -> Sequence[Cat]:
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
    /:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                type: array
                                nullable: false
                                items:
                                    $ref: '#/components/schemas/Cat'
            operationId: home
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
""".strip()
    )


def test_handling_of_generic_with_forward_references(docs: OpenAPIHandler):
    with pytest.warns(UserWarning):
        docs.register_schema_for_type(GenericWithForwardRefExample[Cat])


@pytest.mark.asyncio
async def test_cats_api(docs: OpenAPIHandler, serializer: Serializer):
    app = get_cats_api()
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
    /api/cats:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/PaginatedSetOfCat'
            operationId: get_cats
        post:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/Cat'
            operationId: create_cat
            parameters: []
            requestBody:
                content:
                    application/json:
                        schema:
                            $ref: '#/components/schemas/CreateCatInput'
                required: true
    /api/cats/{cat_id}:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/CatDetails'
            operationId: get_cat_details
            parameters:
            -   name: cat_id
                in: path
                schema:
                    type: integer
                    format: int64
                    nullable: false
                description: ''
                required: true
        delete:
            responses:
                '204':
                    description: Success response
            operationId: delete_cat
            parameters:
            -   name: cat_id
                in: path
                schema:
                    type: integer
                    format: int64
                    nullable: false
                description: ''
                required: true
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
        PaginatedSetOfCat:
            type: object
            required:
            - items
            - total
            properties:
                items:
                    type: array
                    nullable: false
                    items:
                        $ref: '#/components/schemas/Cat'
                total:
                    type: integer
                    format: int64
                    nullable: false
        CreateCatInput:
            type: object
            required:
            - name
            properties:
                name:
                    type: string
                    nullable: false
        CatOwner:
            type: object
            required:
            - id
            - first_name
            - last_name
            properties:
                id:
                    type: integer
                    format: int64
                    nullable: false
                first_name:
                    type: string
                    nullable: false
                last_name:
                    type: string
                    nullable: false
        CatDetails:
            type: object
            required:
            - id
            - name
            - owner
            - friends
            properties:
                id:
                    type: integer
                    format: int64
                    nullable: false
                name:
                    type: string
                    nullable: false
                owner:
                    $ref: '#/components/schemas/CatOwner'
                friends:
                    type: array
                    nullable: false
                    items:
                        type: integer
                        format: int64
                        nullable: false
""".strip()
    )


@pytest.mark.asyncio
async def test_cats_api_capital_operations_ids(
    capitalize_operation_id_docs: CapitalizeOperationDocs,
    serializer: Serializer,
):
    app = get_cats_api()
    docs = capitalize_operation_id_docs

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
    /api/cats:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/PaginatedSetOfCat'
            operationId: Get cats
        post:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/Cat'
            operationId: Create cat
            parameters: []
            requestBody:
                content:
                    application/json:
                        schema:
                            $ref: '#/components/schemas/CreateCatInput'
                required: true
    /api/cats/{cat_id}:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/CatDetails'
            operationId: Get cat details
            parameters:
            -   name: cat_id
                in: path
                schema:
                    type: integer
                    format: int64
                    nullable: false
                description: ''
                required: true
        delete:
            responses:
                '204':
                    description: Success response
            operationId: Delete cat
            parameters:
            -   name: cat_id
                in: path
                schema:
                    type: integer
                    format: int64
                    nullable: false
                description: ''
                required: true
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
        PaginatedSetOfCat:
            type: object
            required:
            - items
            - total
            properties:
                items:
                    type: array
                    nullable: false
                    items:
                        $ref: '#/components/schemas/Cat'
                total:
                    type: integer
                    format: int64
                    nullable: false
        CreateCatInput:
            type: object
            required:
            - name
            properties:
                name:
                    type: string
                    nullable: false
        CatOwner:
            type: object
            required:
            - id
            - first_name
            - last_name
            properties:
                id:
                    type: integer
                    format: int64
                    nullable: false
                first_name:
                    type: string
                    nullable: false
                last_name:
                    type: string
                    nullable: false
        CatDetails:
            type: object
            required:
            - id
            - name
            - owner
            - friends
            properties:
                id:
                    type: integer
                    format: int64
                    nullable: false
                name:
                    type: string
                    nullable: false
                owner:
                    $ref: '#/components/schemas/CatOwner'
                friends:
                    type: array
                    nullable: false
                    items:
                        type: integer
                        format: int64
                        nullable: false
""".strip()
    )
