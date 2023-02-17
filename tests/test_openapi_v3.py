from dataclasses import dataclass
from datetime import date, datetime
from enum import IntEnum
from typing import Generic, List, Optional, Sequence, TypeVar, Union
from uuid import UUID

import pytest
from openapidocs.common import Format, Serializer
from openapidocs.v3 import Info, Reference, Schema, ValueFormat, ValueType
from pydantic import BaseModel, HttpUrl, validator
from pydantic.generics import GenericModel
from pydantic.types import NegativeFloat, PositiveInt, condecimal, confloat, conint

from blacksheep.server.application import Application
from blacksheep.server.bindings import FromForm
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

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class DateTest:
    one: date
    two: datetime


class PydExampleWithSpecificTypes(BaseModel):
    url: HttpUrl


class PydCat(BaseModel):
    id: int
    name: str


class PydPaginatedSetOfCat(BaseModel):
    items: List[PydCat]
    total: int


class PydTypeWithChildModels(BaseModel):
    child: PydPaginatedSetOfCat
    friend: PydExampleWithSpecificTypes


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
class CreateFooInput:
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


class Error(BaseModel):
    code: int
    message: str


class DataModel(BaseModel):
    numbers: List[int]
    people: List[str]


class PydResponse(GenericModel, Generic[T]):
    data: Optional[T]
    error: Optional[Error]

    @validator("error", always=True)
    def check_consistency(cls, v, values):
        if v is not None and values["data"] is not None:
            raise ValueError("must not provide both data and error")
        if v is None and values.get("data") is None:
            raise ValueError("must provide data or error")
        return v


class PydConstrained(BaseModel):
    a: PositiveInt
    b: NegativeFloat
    big_int: conint(gt=1000, lt=1024)

    big_float: confloat(gt=1000, lt=1024)
    unit_interval: confloat(ge=0, le=1)

    decimal_positive: condecimal(gt=0)
    decimal_negative: condecimal(lt=0)


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


def test_dates_handling(docs: OpenAPIHandler, serializer: Serializer):
    docs.register_schema_for_type(DateTest)

    assert docs.components.schemas is not None
    schema = docs.components.schemas["DateTest"]

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
        DateTest:
            type: object
            required:
            - one
            - two
            properties:
                one:
                    type: string
                    format: date
                    nullable: false
                two:
                    type: string
                    format: date-time
                    nullable: false
""".strip()
    )


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
                    nullable: true
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
                    nullable: true
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
                    nullable: true
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
                    nullable: true
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
                    nullable: true
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
async def test_handling_of_pydantic_class_with_generic(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.route("/")
    def home() -> PydPaginatedSetOfCat:
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
                        $ref: '#/components/schemas/PydCat'
                total:
                    type: integer
                    format: int64
                    nullable: false
""".strip()
    )


@pytest.mark.asyncio
async def test_handling_of_pydantic_class_with_child_models(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.route("/")
    def home() -> PydTypeWithChildModels:
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
                                $ref: '#/components/schemas/PydTypeWithChildModels'
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
                        $ref: '#/components/schemas/PydCat'
                total:
                    type: integer
                    format: int64
                    nullable: false
        PydExampleWithSpecificTypes:
            type: object
            required:
            - url
            properties:
                url:
                    type: string
                    format: uri
                    maxLength: 2083
                    minLength: 1
                    nullable: false
        PydTypeWithChildModels:
            type: object
            required:
            - child
            - friend
            properties:
                child:
                    $ref: '#/components/schemas/PydPaginatedSetOfCat'
                friend:
                    $ref: '#/components/schemas/PydExampleWithSpecificTypes'
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


@pytest.mark.asyncio
async def test_handling_of_pydantic_types(docs: OpenAPIHandler, serializer: Serializer):
    app = get_app()

    @app.route("/")
    def home() -> PydExampleWithSpecificTypes:
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
                                $ref: '#/components/schemas/PydExampleWithSpecificTypes'
            operationId: home
components:
    schemas:
        PydExampleWithSpecificTypes:
            type: object
            required:
            - url
            properties:
                url:
                    type: string
                    format: uri
                    maxLength: 2083
                    minLength: 1
                    nullable: false
""".strip()
    )


@pytest.mark.asyncio
async def test_pydantic_generic(docs: OpenAPIHandler, serializer: Serializer):
    app = get_app()

    @app.route("/")
    def home() -> PydResponse[PydCat]:
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
                                $ref: '#/components/schemas/PydResponse[PydCat]'
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
        Error:
            type: object
            required:
            - code
            - message
            properties:
                code:
                    type: integer
                    format: int64
                    nullable: false
                message:
                    type: string
                    nullable: false
        PydResponse[PydCat]:
            type: object
            required:
            - data
            - error
            properties:
                data:
                    $ref: '#/components/schemas/PydCat'
                error:
                    $ref: '#/components/schemas/Error'
""".strip()
    )


@pytest.mark.asyncio
async def test_pydantic_constrained_types(docs: OpenAPIHandler, serializer: Serializer):
    app = get_app()

    @app.route("/")
    def home() -> PydConstrained:
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
                                $ref: '#/components/schemas/PydConstrained'
            operationId: home
components:
    schemas:
        PydConstrained:
            type: object
            required:
            - a
            - b
            - big_int
            - big_float
            - unit_interval
            - decimal_positive
            - decimal_negative
            properties:
                a:
                    type: integer
                    format: int64
                    minimum: 0
                    nullable: false
                b:
                    type: number
                    format: float
                    maximum: 0
                    nullable: false
                big_int:
                    type: integer
                    format: int64
                    maximum: 1024
                    minimum: 1000
                    nullable: false
                big_float:
                    type: number
                    format: float
                    maximum: 1024
                    minimum: 1000
                    nullable: false
                unit_interval:
                    type: number
                    format: float
                    nullable: false
                decimal_positive:
                    type: number
                    format: float
                    minimum: 0
                    nullable: false
                decimal_negative:
                    type: number
                    format: float
                    maximum: 0
                    nullable: false
""".strip()
    )


def test_pydantic_model_handler_does_not_raise_for_array_without_field_info():
    handler = PydanticModelTypeHandler()
    assert handler._open_api_v2_field_schema_to_type(None, {"type": "array"}) is list


def test_pydantic_model_handler_does_not_raise_for_file_type():
    handler = PydanticModelTypeHandler()
    assert handler._open_api_v2_field_schema_to_type(None, {"type": "file"}) == Schema(
        type=ValueType.STRING, format=ValueFormat.BINARY
    )


def test_pydantic_model_handler_defaults_to_empty_schema():
    handler = PydanticModelTypeHandler()
    assert (
        handler._open_api_v2_field_schema_to_type(None, {"type": "unknown"}) == Schema()
    )


def test_pydantic_model_handler_handles_type_without__fields__():
    handler = PydanticModelTypeHandler()

    class Foo:
        @staticmethod
        def schema():
            return {"properties": {"foo": {"type": "boolean"}}}

    handler.get_type_fields(Foo)


@pytest.mark.asyncio
async def test_schema_registration(docs: OpenAPIHandler, serializer: Serializer):
    @docs.register(
        Schema(
            type=ValueType.OBJECT,
            required=["foo"],
            properties={
                "foo": Schema(
                    ValueType.INTEGER, minimum=10, maximum=100, nullable=False
                ),
                "ufo": Schema(
                    ValueType.STRING, min_length=5, max_length=10, nullable=False
                ),
            },
        )
    )
    class A:
        ...

    app = get_app()

    @app.route("/")
    def home() -> A:
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
                                $ref: '#/components/schemas/A'
            operationId: home
components:
    schemas:
        A:
            type: object
            required:
            - foo
            properties:
                foo:
                    type: integer
                    maximum: 100
                    minimum: 10
                    nullable: false
                ufo:
                    type: string
                    maxLength: 10
                    minLength: 5
                    nullable: false
""".strip()
    )


@pytest.mark.asyncio
async def test_handles_ref_for_optional_type(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.route("/cats")
    def one() -> PaginatedSet[Cat]:
        ...

    @app.route("/cats/{cat_id}")
    def two(cat_id: int) -> Optional[Cat]:
        ...

    @app.route("/cats_alt/{cat_id}")
    def three(cat_id: int) -> Cat:
        ...

    @app.route("/cats_value_pattern/{uuid:cat_id}")
    def four(cat_id: UUID) -> Cat:
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
    /cats:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/PaginatedSetOfCat'
            operationId: one
    /cats/{cat_id}:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/Cat'
                '404':
                    description: Object not found
            operationId: two
            parameters:
            -   name: cat_id
                in: path
                schema:
                    type: integer
                    format: int64
                    nullable: false
                description: ''
                required: true
    /cats_alt/{cat_id}:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/Cat'
            operationId: three
            parameters:
            -   name: cat_id
                in: path
                schema:
                    type: integer
                    format: int64
                    nullable: false
                description: ''
                required: true
    /cats_value_pattern/{cat_id}:
        get:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/Cat'
            operationId: four
            parameters:
            -   name: cat_id
                in: path
                schema:
                    type: string
                    format: uuid
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
""".strip()
    )


@pytest.mark.asyncio
async def test_handles_from_form_docs(docs: OpenAPIHandler, serializer: Serializer):
    app = get_app()

    @app.router.post("/foo")
    def one(data: FromForm[CreateFooInput]) -> Foo:
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
    /foo:
        post:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/Foo'
            operationId: one
            parameters: []
            requestBody:
                content:
                    multipart/form-data:
                        schema:
                            $ref: '#/components/schemas/CreateFooInput'
                    application/x-www-form-urlencoded:
                        schema:
                            $ref: '#/components/schemas/CreateFooInput'
                required: true
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
                    nullable: true
                    enum:
                    - 1
                    - 2
                    - 3
        CreateFooInput:
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
                    nullable: true
                    enum:
                    - 1
                    - 2
                    - 3
""".strip()
    )


@pytest.mark.asyncio
async def test_websockets_routes_are_ignored(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.router.post("/foo")
    def one(data: FromForm[CreateFooInput]) -> Foo:
        ...

    @app.router.ws("/ws")
    def websocket_route() -> None:
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
    /foo:
        post:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/Foo'
            operationId: one
            parameters: []
            requestBody:
                content:
                    multipart/form-data:
                        schema:
                            $ref: '#/components/schemas/CreateFooInput'
                    application/x-www-form-urlencoded:
                        schema:
                            $ref: '#/components/schemas/CreateFooInput'
                required: true
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
                    nullable: true
                    enum:
                    - 1
                    - 2
                    - 3
        CreateFooInput:
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
                    nullable: true
                    enum:
                    - 1
                    - 2
                    - 3
""".strip()
    )


@pytest.mark.asyncio
async def test_mount_oad_generation(serializer: Serializer):
    """
    Tests support for OAD generation of mounted apps, using the options:

    parent.mount_registry.auto_events = True
    parent.mount_registry.handle_docs = True
    """
    parent = Application(show_error_details=True)
    parent.mount_registry.auto_events = True
    parent.mount_registry.handle_docs = True

    docs = OpenAPIHandler(info=Info(title="Parent API", version="0.0.1"))
    docs.bind_app(parent)

    @dataclass
    class CreateCatInput:
        name: str
        email: str
        foo: int

    @dataclass
    class CreateDogInput:
        name: str
        email: str
        example: int

    @dataclass
    class CreateParrotInput:
        name: str
        email: str

    @parent.router.get("/")
    def a_home():
        """Parent root."""
        return "Hello, from the parent app - for information, navigate to /docs"

    @parent.router.get("/cats")
    def get_cats_conflicting():
        """Conflict! This will be overridden by the child app route!"""
        return "CONFLICT"

    child_1 = Application()

    @child_1.router.get("/")
    def get_cats():
        """Gets a list of cats."""
        return "Gets a list of cats."

    @child_1.router.post("/")
    def create_cat(data: CreateCatInput):
        """Creates a new cat."""
        return "Creates a new cat."

    @child_1.router.delete("/{cat_id}")
    def delete_cat(cat_id: str):
        """Deletes a cat by id."""
        return "Deletes a cat by id."

    child_2 = Application()

    @child_2.router.get("/")
    def get_dogs():
        """Gets a list of dogs."""
        return "Gets a list of dogs."

    @child_2.router.post("/")
    def create_dog(data: CreateDogInput):
        """Creates a new dog."""
        return "Creates a new dog."

    @child_2.router.delete("/{dog_id}")
    def delete_dog(dog_id: str):
        """Deletes a dog by id."""
        return "Deletes a dog by id."

    child_3 = Application()

    @child_3.router.get("/")
    def get_parrots():
        """Gets a list of parrots."""
        return "Gets a list of parrots"

    @child_3.router.post("/")
    def create_parrot(data: CreateParrotInput):
        """Creates a new parrot."""
        return "Creates a new parrot"

    @child_3.router.delete("/{parrot_id}")
    def delete_parrot(parrot_id: str):
        """Deletes a parrot by id."""
        return "Deletes a parrot by id."

    parent.mount("/cats", child_1)
    parent.mount("/dogs", child_2)
    parent.mount("/parrots", child_3)

    await parent.start()

    yaml = serializer.to_yaml(docs.generate_documentation(parent))

    assert (
        yaml.strip()
        == """
openapi: 3.0.3
info:
    title: Parent API
    version: 0.0.1
paths:
    /:
        get:
            responses: {}
            operationId: a_home
            summary: Parent root.
            description: Parent root.
    /cats:
        get:
            responses: {}
            operationId: get_cats
            summary: Gets a list of cats.
            description: Gets a list of cats.
        post:
            responses: {}
            operationId: create_cat
            summary: Creates a new cat.
            description: Creates a new cat.
            parameters: []
            requestBody:
                content:
                    application/json:
                        schema:
                            $ref: '#/components/schemas/CreateCatInput'
                required: true
    /cats/{cat_id}:
        delete:
            responses: {}
            operationId: delete_cat
            summary: Deletes a cat by id.
            description: Deletes a cat by id.
            parameters:
            -   name: cat_id
                in: path
                schema:
                    type: string
                    nullable: false
                description: ''
                required: true
    /dogs:
        get:
            responses: {}
            operationId: get_dogs
            summary: Gets a list of dogs.
            description: Gets a list of dogs.
        post:
            responses: {}
            operationId: create_dog
            summary: Creates a new dog.
            description: Creates a new dog.
            parameters: []
            requestBody:
                content:
                    application/json:
                        schema:
                            $ref: '#/components/schemas/CreateDogInput'
                required: true
    /dogs/{dog_id}:
        delete:
            responses: {}
            operationId: delete_dog
            summary: Deletes a dog by id.
            description: Deletes a dog by id.
            parameters:
            -   name: dog_id
                in: path
                schema:
                    type: string
                    nullable: false
                description: ''
                required: true
    /parrots:
        get:
            responses: {}
            operationId: get_parrots
            summary: Gets a list of parrots.
            description: Gets a list of parrots.
        post:
            responses: {}
            operationId: create_parrot
            summary: Creates a new parrot.
            description: Creates a new parrot.
            parameters: []
            requestBody:
                content:
                    application/json:
                        schema:
                            $ref: '#/components/schemas/CreateParrotInput'
                required: true
    /parrots/{parrot_id}:
        delete:
            responses: {}
            operationId: delete_parrot
            summary: Deletes a parrot by id.
            description: Deletes a parrot by id.
            parameters:
            -   name: parrot_id
                in: path
                schema:
                    type: string
                    nullable: false
                description: ''
                required: true
components:
    schemas:
        CreateCatInput:
            type: object
            required:
            - name
            - email
            - foo
            properties:
                name:
                    type: string
                    nullable: false
                email:
                    type: string
                    nullable: false
                foo:
                    type: integer
                    format: int64
                    nullable: false
        CreateDogInput:
            type: object
            required:
            - name
            - email
            - example
            properties:
                name:
                    type: string
                    nullable: false
                email:
                    type: string
                    nullable: false
                example:
                    type: integer
                    format: int64
                    nullable: false
        CreateParrotInput:
            type: object
            required:
            - name
            - email
            properties:
                name:
                    type: string
                    nullable: false
                email:
                    type: string
                    nullable: false
""".strip()
    )


@pytest.mark.asyncio
async def test_mount_oad_generation_sub_children(serializer: Serializer):
    """
    Tests support for OAD generation of mounted apps, using the options:

    parent.mount_registry.auto_events = True
    parent.mount_registry.handle_docs = True
    """
    parent = Application(show_error_details=True)
    parent.mount_registry.auto_events = True
    parent.mount_registry.handle_docs = True

    docs = OpenAPIHandler(info=Info(title="Parent API", version="0.0.1"))
    docs.bind_app(parent)

    @parent.router.get("/")
    def a_home():
        """Parent root."""
        return "Hello, from the parent app - for information, navigate to /docs"

    child_1 = Application()
    child_2 = Application()
    child_3 = Application()

    @child_1.router.get("/")
    def child_1_home():
        return "Child 1 home."

    @child_2.router.get("/")
    def child_2_home():
        return "Child 2 home."

    @child_3.router.get("/")
    def child_3_home():
        return "Child 3 home."

    child_1.mount_registry.auto_events = True
    child_1.mount_registry.handle_docs = True
    child_2.mount_registry.auto_events = True
    child_2.mount_registry.handle_docs = True

    parent.mount("/child-1", child_1)
    child_1.mount("/child-2", child_2)
    child_2.mount("/child-3", child_3)

    await parent.start()

    yaml = serializer.to_yaml(docs.generate_documentation(parent))

    assert (
        yaml.strip()
        == """
openapi: 3.0.3
info:
    title: Parent API
    version: 0.0.1
paths:
    /:
        get:
            responses: {}
            operationId: a_home
            summary: Parent root.
            description: Parent root.
    /child-1:
        get:
            responses: {}
            operationId: child_1_home
    /child-1/child-2:
        get:
            responses: {}
            operationId: child_2_home
    /child-1/child-2/child-3:
        get:
            responses: {}
            operationId: child_3_home
components: {}
""".strip()
    )
