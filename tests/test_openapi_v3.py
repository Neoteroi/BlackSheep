from dataclasses import dataclass
from datetime import date, datetime
from enum import IntEnum
from typing import Generic, List, Mapping, Optional, Sequence, TypeVar, Union
from uuid import UUID

import pytest
from openapidocs.common import Format, Serializer
from openapidocs.v3 import (
    APIKeySecurity,
    HTTPSecurity,
    Info,
    OAuth2Security,
    OAuthFlow,
    OAuthFlows,
    OpenIdConnectSecurity,
    ParameterLocation,
    Reference,
    Schema,
    ValueType,
)
from pydantic import VERSION as PYDANTIC_LIB_VERSION
from pydantic import BaseModel, HttpUrl
from pydantic.types import (
    UUID4,
    NegativeFloat,
    PositiveInt,
    condecimal,
    confloat,
    conint,
)

from blacksheep.server.application import Application
from blacksheep.server.bindings import FromForm
from blacksheep.server.controllers import APIController
from blacksheep.server.openapi.common import (
    ContentInfo,
    DefaultSerializer,
    EndpointDocs,
    OpenAPIEndpointException,
    ResponseInfo,
    SecurityInfo,
)
from blacksheep.server.openapi.exceptions import DuplicatedContentTypeDocsException
from blacksheep.server.openapi.v3 import (
    DataClassTypeHandler,
    OpenAPIHandler,
    PydanticModelTypeHandler,
    Tag,
    check_union,
)
from blacksheep.server.routing import RoutesRegistry

GenericModel = BaseModel

PYDANTIC_VERSION = 2

if int(PYDANTIC_LIB_VERSION[0]) < 2:
    from pydantic.generics import GenericModel

    PYDANTIC_VERSION = 1

try:
    from pydantic import field_validator
except ImportError:
    # Pydantic v1
    from pydantic import validator as field_validator


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
    childs: list[UUID4]


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
class CreateCatImages:
    images: List[str]


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

    @field_validator("error")
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

    big_float: confloat(gt=1000.0, lt=1024.0)
    unit_interval: confloat(ge=0, le=1)

    decimal_positive: condecimal(gt=0)
    decimal_negative: condecimal(lt=0)


def get_app() -> Application:
    app = Application()
    app.controllers_router = RoutesRegistry()
    return app


def get_cats_api() -> Application:
    app = get_app()
    get = app.router.get
    post = app.router.post
    delete = app.router.delete

    @get("/api/cats")
    def get_cats() -> PaginatedSet[Cat]: ...

    @get("/api/cats/{cat_id}")
    def get_cat_details(cat_id: int) -> CatDetails: ...

    @post("/api/cats")
    def create_cat(input: CreateCatInput) -> Cat: ...

    @delete("/api/cats/{cat_id}")
    def delete_cat(cat_id: int) -> None: ...

    @post("/api/cats/{cat_id}/images")
    def upload_images(cat_id: int, images: FromForm[CreateCatImages]) -> None: ...

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


async def test_raises_for_started_app(docs):
    app = get_app()

    await app.start()

    with pytest.raises(TypeError):
        docs.bind_app(app)


async def test_raises_for_duplicated_content_example(docs):
    app = get_app()

    @app.router.get("/")
    @docs(
        responses={
            200: ResponseInfo("Example", content=[ContentInfo(Foo), ContentInfo(Foo)])
        }
    )
    async def example(): ...

    with pytest.raises(DuplicatedContentTypeDocsException):
        docs.bind_app(app)
        await app.start()


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

    yaml = serializer.to_yaml(docs.generate_documentation(get_app()))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
tags: []
""".strip()
    )


def test_register_schema_for_generic_with_list(
    docs: OpenAPIHandler, serializer: Serializer
):
    docs.register_schema_for_type(PaginatedSet[Foo])

    assert docs.components.schemas is not None
    schema = docs.components.schemas["PaginatedSetOfFoo"]

    assert isinstance(schema, Schema)

    yaml = serializer.to_yaml(docs.generate_documentation(get_app()))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
tags: []
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

    yaml = serializer.to_yaml(docs.generate_documentation(get_app()))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
tags: []
""".strip()
    )


def test_register_schema_for_generic_with_property(
    docs: OpenAPIHandler, serializer: Serializer
):
    docs.register_schema_for_type(Validated[Foo])

    assert docs.components.schemas is not None
    schema = docs.components.schemas["ValidatedOfFoo"]

    assert isinstance(schema, Schema)

    yaml = serializer.to_yaml(docs.generate_documentation(get_app()))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
tags: []
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

    yaml = serializer.to_yaml(docs.generate_documentation(get_app()))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
tags: []
""".strip()
    )


async def test_register_schema_for_multi_generic(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.router.route("/combo")
    def combo_example() -> Combo[Cat, Foo]: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
tags: []
""".strip()
    )


async def test_register_schema_for_generic_with_list_reusing_ref(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()
    docs.bind_app(app)

    @docs(tags=["B tag"])
    @app.router.route("/one")
    def one() -> PaginatedSet[Cat]: ...

    @docs(tags=["A tag"])
    @app.router.route("/two")
    def two() -> PaginatedSet[Cat]: ...

    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
            tags:
            - B tag
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
            tags:
            - A tag
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
tags:
-   name: A tag
-   name: B tag
""".strip()
    )


def test_get_type_name_raises_for_invalid_object_type(docs: OpenAPIHandler):
    with pytest.raises(ValueError):
        docs.get_type_name(10)


async def test_handling_of_forward_references(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.router.route("/")
    def forward_ref_example() -> ForwardRefExample: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
tags: []
""".strip()
    )


async def test_handling_of_normal_class(docs: OpenAPIHandler, serializer: Serializer):
    """
    Plain classes are simply ignored, since their handling would be ambiguous:
    should the library inspect type annotations, __dict__?
    (in fact, the built-in json module throws for them).
    """
    app = get_app()

    @app.router.route("/")
    def plain_class() -> PlainClass: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
tags: []
""".strip()
    )


async def test_handling_of_pydantic_class_with_generic(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.router.route("/")
    def home() -> PydPaginatedSetOfCat: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    if PYDANTIC_VERSION == 1:
        assert (
            yaml.strip()
            == """
openapi: 3.1.0
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
            title: PydCat
            type: object
            properties:
                id:
                    title: Id
                    type: integer
                name:
                    title: Name
                    type: string
                childs:
                    title: Childs
                    type: array
                    items:
                        type: string
                        format: uuid4
            required:
            - id
            - name
            - childs
        PydPaginatedSetOfCat:
            title: PydPaginatedSetOfCat
            type: object
            properties:
                items:
                    title: Items
                    type: array
                    items:
                        $ref: '#/components/schemas/PydCat'
                total:
                    title: Total
                    type: integer
            required:
            - items
            - total
tags: []
""".strip()
        )
    else:
        assert (
            yaml.strip()
            == """
openapi: 3.1.0
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
            properties:
                id:
                    title: Id
                    type: integer
                name:
                    title: Name
                    type: string
                childs:
                    items:
                        format: uuid4
                        type: string
                    title: Childs
                    type: array
            required:
            - id
            - name
            - childs
            title: PydCat
            type: object
        PydPaginatedSetOfCat:
            properties:
                items:
                    items:
                        $ref: '#/components/schemas/PydCat'
                    title: Items
                    type: array
                total:
                    title: Total
                    type: integer
            required:
            - items
            - total
            title: PydPaginatedSetOfCat
            type: object
tags: []
""".strip()
        )


async def test_handling_of_pydantic_class_with_child_models(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.router.route("/")
    def home() -> PydTypeWithChildModels: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    if PYDANTIC_VERSION == 1:
        assert (
            yaml.strip()
            == """
openapi: 3.1.0
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
            title: PydCat
            type: object
            properties:
                id:
                    title: Id
                    type: integer
                name:
                    title: Name
                    type: string
                childs:
                    title: Childs
                    type: array
                    items:
                        type: string
                        format: uuid4
            required:
            - id
            - name
            - childs
        PydPaginatedSetOfCat:
            title: PydPaginatedSetOfCat
            type: object
            properties:
                items:
                    title: Items
                    type: array
                    items:
                        $ref: '#/components/schemas/PydCat'
                total:
                    title: Total
                    type: integer
            required:
            - items
            - total
        PydExampleWithSpecificTypes:
            title: PydExampleWithSpecificTypes
            type: object
            properties:
                url:
                    title: Url
                    minLength: 1
                    maxLength: 2083
                    format: uri
                    type: string
            required:
            - url
        PydTypeWithChildModels:
            title: PydTypeWithChildModels
            type: object
            properties:
                child:
                    $ref: '#/components/schemas/PydPaginatedSetOfCat'
                friend:
                    $ref: '#/components/schemas/PydExampleWithSpecificTypes'
            required:
            - child
            - friend
tags: []
    """.strip()
        )
    else:
        assert (
            yaml.strip()
            == """
openapi: 3.1.0
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
            properties:
                id:
                    title: Id
                    type: integer
                name:
                    title: Name
                    type: string
                childs:
                    items:
                        format: uuid4
                        type: string
                    title: Childs
                    type: array
            required:
            - id
            - name
            - childs
            title: PydCat
            type: object
        PydExampleWithSpecificTypes:
            properties:
                url:
                    format: uri
                    maxLength: 2083
                    minLength: 1
                    title: Url
                    type: string
            required:
            - url
            title: PydExampleWithSpecificTypes
            type: object
        PydPaginatedSetOfCat:
            properties:
                items:
                    items:
                        $ref: '#/components/schemas/PydCat'
                    title: Items
                    type: array
                total:
                    title: Total
                    type: integer
            required:
            - items
            - total
            title: PydPaginatedSetOfCat
            type: object
        PydTypeWithChildModels:
            properties:
                child:
                    $ref: '#/components/schemas/PydPaginatedSetOfCat'
                friend:
                    $ref: '#/components/schemas/PydExampleWithSpecificTypes'
            required:
            - child
            - friend
            title: PydTypeWithChildModels
            type: object
tags: []
    """.strip()
        )


async def test_handling_of_pydantic_class_in_generic(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.router.route("/")
    def home() -> PaginatedSet[PydCat]: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    if PYDANTIC_VERSION == 1:
        assert (
            yaml.strip()
            == """
openapi: 3.1.0
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
            title: PydCat
            type: object
            properties:
                id:
                    title: Id
                    type: integer
                name:
                    title: Name
                    type: string
                childs:
                    title: Childs
                    type: array
                    items:
                        type: string
                        format: uuid4
            required:
            - id
            - name
            - childs
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
tags: []
    """.strip()
        )
    else:
        assert (
            yaml.strip()
            == """
openapi: 3.1.0
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
            properties:
                id:
                    title: Id
                    type: integer
                name:
                    title: Name
                    type: string
                childs:
                    items:
                        format: uuid4
                        type: string
                    title: Childs
                    type: array
            required:
            - id
            - name
            - childs
            title: PydCat
            type: object
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
tags: []
""".strip()
        )


async def test_handling_of_sequence(docs: OpenAPIHandler, serializer: Serializer):
    app = get_app()

    @app.router.route("/")
    def home() -> Sequence[Cat]: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
tags: []
""".strip()
    )


@pytest.mark.asyncio
async def test_handling_of_mapping(docs: OpenAPIHandler, serializer: Serializer):
    app = get_app()

    @app.router.route("/")
    def home() -> Mapping[str, Mapping[int, List[Cat]]]: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    assert (
        yaml.strip()
        == r"""
openapi: 3.1.0
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
                                type: object
                                additionalProperties:
                                    type: object
                                    additionalProperties:
                                        type: array
                                        nullable: false
                                        items:
                                            $ref: '#/components/schemas/Cat'
                                    nullable: false
                                nullable: false
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
tags: []
""".strip()
    )


def test_handling_of_generic_with_forward_references(docs: OpenAPIHandler):
    with pytest.warns(UserWarning):
        docs.register_schema_for_type(GenericWithForwardRefExample[Cat])


async def test_cats_api(docs: OpenAPIHandler, serializer: Serializer):
    app = get_cats_api()
    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
    /api/cats/{cat_id}/images:
        post:
            responses:
                '204':
                    description: Success response
            operationId: upload_images
            parameters:
            -   name: cat_id
                in: path
                schema:
                    type: integer
                    format: int64
                    nullable: false
                description: ''
                required: true
            requestBody:
                content:
                    multipart/form-data:
                        schema:
                            $ref: '#/components/schemas/CreateCatImages'
                    application/x-www-form-urlencoded:
                        schema:
                            $ref: '#/components/schemas/CreateCatImages'
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
        CreateCatImages:
            type: object
            required:
            - images
            properties:
                images:
                    type: array
                    nullable: false
                    items:
                        type: string
                        nullable: false
tags: []
""".strip()
    )


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
openapi: 3.1.0
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
    /api/cats/{cat_id}/images:
        post:
            responses:
                '204':
                    description: Success response
            operationId: Upload images
            parameters:
            -   name: cat_id
                in: path
                schema:
                    type: integer
                    format: int64
                    nullable: false
                description: ''
                required: true
            requestBody:
                content:
                    multipart/form-data:
                        schema:
                            $ref: '#/components/schemas/CreateCatImages'
                    application/x-www-form-urlencoded:
                        schema:
                            $ref: '#/components/schemas/CreateCatImages'
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
        CreateCatImages:
            type: object
            required:
            - images
            properties:
                images:
                    type: array
                    nullable: false
                    items:
                        type: string
                        nullable: false
tags: []
""".strip()
    )


async def test_handling_of_pydantic_types(docs: OpenAPIHandler, serializer: Serializer):
    app = get_app()

    @app.router.route("/")
    def home() -> PydExampleWithSpecificTypes: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    if PYDANTIC_VERSION == 1:
        assert (
            yaml.strip()
            == """
openapi: 3.1.0
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
            title: PydExampleWithSpecificTypes
            type: object
            properties:
                url:
                    title: Url
                    minLength: 1
                    maxLength: 2083
                    format: uri
                    type: string
            required:
            - url
tags: []
""".strip()
        )
        return

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
            properties:
                url:
                    format: uri
                    maxLength: 2083
                    minLength: 1
                    title: Url
                    type: string
            required:
            - url
            title: PydExampleWithSpecificTypes
            type: object
tags: []
""".strip()
    )


async def test_pydantic_generic(docs: OpenAPIHandler, serializer: Serializer):
    app = get_app()

    @app.router.route("/")
    def home() -> PydResponse[PydCat]: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    if PYDANTIC_VERSION == 1:
        expected_result = """
openapi: 3.1.0
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
            title: PydCat
            type: object
            properties:
                id:
                    title: Id
                    type: integer
                name:
                    title: Name
                    type: string
                childs:
                    title: Childs
                    type: array
                    items:
                        type: string
                        format: uuid4
            required:
            - id
            - name
            - childs
        Error:
            title: Error
            type: object
            properties:
                code:
                    title: Code
                    type: integer
                message:
                    title: Message
                    type: string
            required:
            - code
            - message
        PydResponse[PydCat]:
            title: PydResponse[PydCat]
            type: object
            properties:
                data:
                    $ref: '#/components/schemas/PydCat'
                error:
                    $ref: '#/components/schemas/Error'
tags: []
""".strip()
    elif PYDANTIC_VERSION == 2:
        expected_result = """
openapi: 3.1.0
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
        Error:
            properties:
                code:
                    title: Code
                    type: integer
                message:
                    title: Message
                    type: string
            required:
            - code
            - message
            title: Error
            type: object
        PydCat:
            properties:
                id:
                    title: Id
                    type: integer
                name:
                    title: Name
                    type: string
                childs:
                    items:
                        format: uuid4
                        type: string
                    title: Childs
                    type: array
            required:
            - id
            - name
            - childs
            title: PydCat
            type: object
        PydResponse[PydCat]:
            properties:
                data:
                    anyOf:
                    -   $ref: '#/components/schemas/PydCat'
                    -   type: 'null'
                error:
                    anyOf:
                    -   $ref: '#/components/schemas/Error'
                    -   type: 'null'
            required:
            - data
            - error
            title: PydResponse[PydCat]
            type: object
tags: []
""".strip()
    else:
        raise RuntimeError("Missing expected_result")
    assert yaml.strip() == expected_result


async def test_pydantic_constrained_types(docs: OpenAPIHandler, serializer: Serializer):
    app = get_app()

    @app.router.route("/")
    def home() -> PydConstrained: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))
    expected_result: str

    if PYDANTIC_VERSION == 1:
        expected_result = """
openapi: 3.1.0
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
            title: PydConstrained
            type: object
            properties:
                a:
                    title: A
                    exclusiveMinimum: 0
                    type: integer
                b:
                    title: B
                    exclusiveMaximum: 0
                    type: number
                big_int:
                    title: Big Int
                    exclusiveMinimum: 1000
                    exclusiveMaximum: 1024
                    type: integer
                big_float:
                    title: Big Float
                    exclusiveMinimum: 1000.0
                    exclusiveMaximum: 1024.0
                    type: number
                unit_interval:
                    title: Unit Interval
                    minimum: 0
                    maximum: 1
                    type: number
                decimal_positive:
                    title: Decimal Positive
                    exclusiveMinimum: 0
                    type: number
                decimal_negative:
                    title: Decimal Negative
                    exclusiveMaximum: 0
                    type: number
            required:
            - a
            - b
            - big_int
            - big_float
            - unit_interval
            - decimal_positive
            - decimal_negative
tags: []
""".strip()
    elif PYDANTIC_VERSION == 2:
        expected_result = """
openapi: 3.1.0
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
            properties:
                a:
                    exclusiveMinimum: 0
                    title: A
                    type: integer
                b:
                    exclusiveMaximum: 0
                    title: B
                    type: number
                big_int:
                    exclusiveMaximum: 1024
                    exclusiveMinimum: 1000
                    title: Big Int
                    type: integer
                big_float:
                    exclusiveMaximum: 1024.0
                    exclusiveMinimum: 1000.0
                    title: Big Float
                    type: number
                unit_interval:
                    maximum: 1
                    minimum: 0
                    title: Unit Interval
                    type: number
                decimal_positive:
                    anyOf:
                    -   exclusiveMinimum: 0.0
                        type: number
                    -   type: string
                    title: Decimal Positive
                decimal_negative:
                    anyOf:
                    -   exclusiveMaximum: 0.0
                        type: number
                    -   type: string
                    title: Decimal Negative
            required:
            - a
            - b
            - big_int
            - big_float
            - unit_interval
            - decimal_positive
            - decimal_negative
            title: PydConstrained
            type: object
tags: []
    """.strip()
    assert yaml.strip() == expected_result


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
    class A: ...

    app = get_app()

    @app.router.route("/")
    def home() -> A: ...

    @docs(
        security=[
            SecurityInfo("basicAuth", []),
            SecurityInfo("bearerAuth", ["read:home", "write:home"]),
        ]
    )
    @app.router.route("/", methods=["POST"])
    def auth_home() -> A: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
        post:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/A'
            operationId: auth_home
            security:
            -   basicAuth: []
            -   bearerAuth:
                - read:home
                - write:home
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
tags: []
""".strip()
    )


async def test_handles_ref_for_optional_type(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.router.route("/cats")
    def one() -> PaginatedSet[Cat]: ...

    @app.router.route("/cats/{cat_id}")
    def two(cat_id: int) -> Optional[Cat]: ...

    @app.router.route("/cats_alt/{cat_id}")
    def three(cat_id: int) -> Cat: ...

    @app.router.route("/cats_value_pattern/{uuid:cat_id}")
    def four(cat_id: UUID) -> Cat: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
tags: []
""".strip()
    )


async def test_handles_from_form_docs(docs: OpenAPIHandler, serializer: Serializer):
    app = get_app()

    @app.router.post("/foo")
    def one(data: FromForm[CreateFooInput]) -> Foo: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
tags: []
""".strip()
    )


async def test_websockets_routes_are_ignored(
    docs: OpenAPIHandler, serializer: Serializer
):
    app = get_app()

    @app.router.post("/foo")
    def one(data: FromForm[CreateFooInput]) -> Foo: ...

    @app.router.ws("/ws")
    def websocket_route() -> None: ...

    docs.bind_app(app)
    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
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
tags: []
""".strip()
    )


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
openapi: 3.1.0
info:
    title: Parent API
    version: 0.0.1
paths:
    /:
        get:
            responses: {}
            summary: Parent root.
            description: Parent root.
            operationId: a_home
    /cats:
        get:
            responses: {}
            summary: Gets a list of cats.
            description: Gets a list of cats.
            operationId: get_cats
        post:
            responses: {}
            summary: Creates a new cat.
            description: Creates a new cat.
            operationId: create_cat
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
            summary: Deletes a cat by id.
            description: Deletes a cat by id.
            operationId: delete_cat
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
            summary: Gets a list of dogs.
            description: Gets a list of dogs.
            operationId: get_dogs
        post:
            responses: {}
            summary: Creates a new dog.
            description: Creates a new dog.
            operationId: create_dog
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
            summary: Deletes a dog by id.
            description: Deletes a dog by id.
            operationId: delete_dog
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
            summary: Gets a list of parrots.
            description: Gets a list of parrots.
            operationId: get_parrots
        post:
            responses: {}
            summary: Creates a new parrot.
            description: Creates a new parrot.
            operationId: create_parrot
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
            summary: Deletes a parrot by id.
            description: Deletes a parrot by id.
            operationId: delete_parrot
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
tags: []
""".strip()
    )


async def test_mount_oad_generation_sub_children(serializer: Serializer):
    """
    Tests support for OAD generation of mounted apps, using the options:

    parent.mount_registry.auto_events = True
    parent.mount_registry.handle_docs = True
    """
    parent = Application(show_error_details=True)
    parent.mount_registry.auto_events = True
    parent.mount_registry.handle_docs = True

    docs = OpenAPIHandler(
        info=Info(title="Parent API", version="0.0.1"),
        tags=[Tag(name="A Home")],
    )
    docs.bind_app(parent)

    @docs(tags=["A Home"])
    @parent.router.get("/")
    def a_home():
        """Parent root."""
        return "Hello, from the parent app - for information, navigate to /docs"

    child_1 = Application()
    child_2 = Application()
    child_3 = Application()

    @docs(tags=["Child z Home"])
    @child_1.router.get("/")
    def child_1_home():
        return "Child 1 home."

    @docs(tags=["Child y Home"])
    @child_2.router.get("/")
    def child_2_home():
        return "Child 2 home."

    @docs(tags=["Child x Home"])
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
openapi: 3.1.0
info:
    title: Parent API
    version: 0.0.1
paths:
    /:
        get:
            responses: {}
            tags:
            - A Home
            summary: Parent root.
            description: Parent root.
            operationId: a_home
    /child-1:
        get:
            responses: {}
            tags:
            - Child z Home
            operationId: child_1_home
    /child-1/child-2:
        get:
            responses: {}
            tags:
            - Child y Home
            operationId: child_2_home
    /child-1/child-2/child-3:
        get:
            responses: {}
            tags:
            - Child x Home
            operationId: child_3_home
components: {}
tags:
-   name: A Home
""".strip()
    )


async def test_sorting_api_controllers_tags(serializer: Serializer):
    app = get_app()
    get = app.controllers_router.get
    post = app.controllers_router.post

    docs = OpenAPIHandler(
        info=Info(
            title="Example API",
            version="0.0.1",
        ),
        security_schemes={
            "basicAuth": HTTPSecurity(
                scheme="basic",
                description="Basic Auth",
            ),
            "bearerAuth": HTTPSecurity(
                scheme="bearer",
                description="Bearer Auth",
            ),
            "apiKeyAuth": APIKeySecurity(
                in_=ParameterLocation.HEADER,
                name="X-API-Key",
                description="API Key Auth",
            ),
            "openID": OpenIdConnectSecurity(
                open_id_connect_url="https://example.com",
                description="OIDC Auth",
            ),
            "oauth2": OAuth2Security(
                flows=OAuthFlows(
                    implicit=OAuthFlow(
                        authorization_url="https://example.com/oauth2/authorize",
                        token_url="https://example.com/oauth2/token",
                        refresh_url="https://example.com/oauth2/refresh",
                        scopes={
                            "read:cats": "Read your cats",
                            "write:cats": "Write your cats",
                        },
                    )
                ),
                description="OAuth2 Auth",
            ),
        },
    )
    docs.bind_app(app)

    @dataclass
    class Cat:
        pass

    @dataclass
    class Dog:
        pass

    @dataclass
    class Parrot:
        pass

    class Parrots(APIController):
        @get()
        def get_parrots(self) -> List[Parrot]:
            """Return the list of configured Parrots."""

        @post()
        def create_parrot(self, parrot: Parrot) -> None:
            """Add a Parrot to the system."""

    class Dogs(APIController):
        @get()
        def get_dogs(self) -> List[Dog]:
            """Return the list of configured dogs."""

        @post()
        def create_dog(self, dog: Dog) -> None:
            """Add a Dog to the system."""

    class Cats(APIController):
        @get()
        def get_cats(self) -> List[Cat]:
            """Return the list of configured cats."""

        @post()
        def create_cat(self, cat: Cat) -> None:
            """Add a Cat to the system."""

    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    assert (
        yaml.strip()
        == """
openapi: 3.1.0
info:
    title: Example API
    version: 0.0.1
paths:
    /api/parrots:
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
                                    $ref: '#/components/schemas/Parrot'
            tags:
            - Parrots
            summary: Return the list of configured Parrots.
            description: Return the list of configured Parrots.
            operationId: get_parrots
            parameters: []
        post:
            responses:
                '204':
                    description: Success response
            tags:
            - Parrots
            summary: Add a Parrot to the system.
            description: Add a Parrot to the system.
            operationId: create_parrot
            parameters: []
            requestBody:
                content:
                    application/json:
                        schema:
                            $ref: '#/components/schemas/Parrot'
                required: true
    /api/dogs:
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
                                    $ref: '#/components/schemas/Dog'
            tags:
            - Dogs
            summary: Return the list of configured dogs.
            description: Return the list of configured dogs.
            operationId: get_dogs
            parameters: []
        post:
            responses:
                '204':
                    description: Success response
            tags:
            - Dogs
            summary: Add a Dog to the system.
            description: Add a Dog to the system.
            operationId: create_dog
            parameters: []
            requestBody:
                content:
                    application/json:
                        schema:
                            $ref: '#/components/schemas/Dog'
                required: true
    /api/cats:
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
            tags:
            - Cats
            summary: Return the list of configured cats.
            description: Return the list of configured cats.
            operationId: get_cats
            parameters: []
        post:
            responses:
                '204':
                    description: Success response
            tags:
            - Cats
            summary: Add a Cat to the system.
            description: Add a Cat to the system.
            operationId: create_cat
            parameters: []
            requestBody:
                content:
                    application/json:
                        schema:
                            $ref: '#/components/schemas/Cat'
                required: true
components:
    schemas:
        Parrot:
            type: object
            properties: {}
        Dog:
            type: object
            properties: {}
        Cat:
            type: object
            properties: {}
    securitySchemes:
        basicAuth:
            scheme: basic
            type: http
            description: Basic Auth
        bearerAuth:
            scheme: bearer
            type: http
            description: Bearer Auth
        apiKeyAuth:
            name: X-API-Key
            in: header
            type: apiKey
            description: API Key Auth
        openID:
            openIdConnectUrl: https://example.com
            type: openIdConnect
            description: OIDC Auth
        oauth2:
            flows:
                implicit:
                    scopes:
                        read:cats: Read your cats
                        write:cats: Write your cats
                    authorizationUrl: https://example.com/oauth2/authorize
                    tokenUrl: https://example.com/oauth2/token
                    refreshUrl: https://example.com/oauth2/refresh
            type: oauth2
            description: OAuth2 Auth
tags:
-   name: Cats
-   name: Dogs
-   name: Parrots
""".strip()
    )


@dataclass
class A:
    a_prop: int


@dataclass
class B:
    b_prop: str


@dataclass
class C:
    c_prop: str


@dataclass
class D:
    d_prop: float


@dataclass
class E:
    e_prop: int


@dataclass
class F:
    f_prop: str
    f_prop2: A


@dataclass
class AnyOfTestClass:
    sub_prop: Union[A, B, C]


@dataclass
class AnyOfResponseTestClass:
    data: Union[D, E, F]


class APyd(BaseModel):
    a_prop: int


class BPyd(BaseModel):
    b_prop: str


class CPyd(BaseModel):
    c_prop: str


class DPyd(BaseModel):
    d_prop: float


class EPyd(BaseModel):
    e_prop: int


class FPyd(BaseModel):
    f_prop: str
    f_prop2: APyd


class AnyOfTestClassPyd(BaseModel):
    sub_prop: Union[APyd, BPyd, CPyd]


class AnyOfResponseTestClassPyd(BaseModel):
    data: Union[DPyd, EPyd, FPyd]


async def test_any_of_dataclasses(docs: OpenAPIHandler, serializer: Serializer):
    app = get_app()
    docs.bind_app(app)

    @app.router.post("/one")
    def one(data: AnyOfTestClass) -> AnyOfResponseTestClass: ...

    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    expected_fragments = [
        """
    /one:
        post:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/AnyOfResponseTestClass'
            operationId: one
            parameters: []
            requestBody:
                content:
                    application/json:
                        schema:
                            $ref: '#/components/schemas/AnyOfTestClass'
                required: true
        """,
        """
        D:
            type: object
            required:
            - d_prop
            properties:
                d_prop:
                    type: number
                    format: float
                    nullable: false
        """,
        """
        UnionOfDAndEAndF:
            type: object
            anyOf:
            -   $ref: '#/components/schemas/D'
            -   $ref: '#/components/schemas/E'
            -   $ref: '#/components/schemas/F'
        """,
        """
        AnyOfResponseTestClass:
            type: object
            properties:
                data:
                    $ref: '#/components/schemas/UnionOfDAndEAndF'
        """,
        """
        UnionOfAAndBAndC:
            type: object
            anyOf:
            -   $ref: '#/components/schemas/A'
            -   $ref: '#/components/schemas/B'
            -   $ref: '#/components/schemas/C'
        """,
    ]

    for fragment in expected_fragments:
        assert fragment.strip() in yaml


async def test_any_of_pydantic_models(docs: OpenAPIHandler, serializer: Serializer):
    app = get_app()
    docs.bind_app(app)

    @app.router.post("/one")
    def one(data: AnyOfTestClassPyd) -> AnyOfResponseTestClassPyd: ...

    await app.start()

    yaml = serializer.to_yaml(docs.generate_documentation(app))

    expected_fragments = [
        """
openapi: 3.1.0
info:
    title: Example
    version: 0.0.1
paths:
    /one:
        post:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/AnyOfResponseTestClassPyd'
            operationId: one
            parameters: []
            requestBody:
                content:
                    application/json:
                        schema:
                            $ref: '#/components/schemas/AnyOfTestClassPyd'
                required: true
components:
    schemas:
        APyd:
            properties:
                a_prop:
                    title: A Prop
                    type: integer
            required:
            - a_prop
            title: APyd
            type: object
        DPyd:
            properties:
                d_prop:
                    title: D Prop
                    type: number
            required:
            - d_prop
            title: DPyd
            type: object
        EPyd:
            properties:
                e_prop:
                    title: E Prop
                    type: integer
            required:
            - e_prop
            title: EPyd
            type: object
        FPyd:
            properties:
                f_prop:
                    title: F Prop
                    type: string
                f_prop2:
                    $ref: '#/components/schemas/APyd'
            required:
            - f_prop
            - f_prop2
            title: FPyd
            type: object
        AnyOfResponseTestClassPyd:
            properties:
                data:
                    anyOf:
                    -   $ref: '#/components/schemas/DPyd'
                    -   $ref: '#/components/schemas/EPyd'
                    -   $ref: '#/components/schemas/FPyd'
                    title: Data
            required:
            - data
            title: AnyOfResponseTestClassPyd
            type: object
        BPyd:
            properties:
                b_prop:
                    title: B Prop
                    type: string
            required:
            - b_prop
            title: BPyd
            type: object
        CPyd:
            properties:
                c_prop:
                    title: C Prop
                    type: string
            required:
            - c_prop
            title: CPyd
            type: object
        AnyOfTestClassPyd:
            properties:
                sub_prop:
                    anyOf:
                    -   $ref: '#/components/schemas/APyd'
                    -   $ref: '#/components/schemas/BPyd'
                    -   $ref: '#/components/schemas/CPyd'
                    title: Sub Prop
            required:
            - sub_prop
            title: AnyOfTestClassPyd
            type: object
tags: []
        """.strip(),
    ]

    if PYDANTIC_VERSION == 1:
        expected_fragments = [
            """
    /one:
        post:
            responses:
                '200':
                    description: Success response
                    content:
                        application/json:
                            schema:
                                $ref: '#/components/schemas/AnyOfResponseTestClassPyd'
            operationId: one
            parameters: []
            requestBody:
                content:
                    application/json:
                        schema:
                            $ref: '#/components/schemas/AnyOfTestClassPyd'
                required: true
            """,
            """
components:
    schemas:
        DPyd:
            title: DPyd
            type: object
            properties:
                d_prop:
                    title: D Prop
                    type: number
            required:
            - d_prop
        EPyd:
            title: EPyd
            type: object
            properties:
                e_prop:
                    title: E Prop
                    type: integer
            required:
            - e_prop
        APyd:
            title: APyd
            type: object
            properties:
                a_prop:
                    title: A Prop
                    type: integer
            required:
            - a_prop
        FPyd:
            title: FPyd
            type: object
            properties:
                f_prop:
                    title: F Prop
                    type: string
                f_prop2:
                    $ref: '#/components/schemas/APyd'
            required:
            - f_prop
            - f_prop2
        AnyOfResponseTestClassPyd:
            title: AnyOfResponseTestClassPyd
            type: object
            properties:
                data:
                    title: Data
                    anyOf:
                    -   $ref: '#/components/schemas/DPyd'
                    -   $ref: '#/components/schemas/EPyd'
                    -   $ref: '#/components/schemas/FPyd'
            required:
            - data
        BPyd:
            title: BPyd
            type: object
            properties:
                b_prop:
                    title: B Prop
                    type: string
            required:
            - b_prop
        CPyd:
            title: CPyd
            type: object
            properties:
                c_prop:
                    title: C Prop
                    type: string
            required:
            - c_prop
        AnyOfTestClassPyd:
            title: AnyOfTestClassPyd
            type: object
            properties:
                sub_prop:
                    title: Sub Prop
                    anyOf:
                    -   $ref: '#/components/schemas/APyd'
                    -   $ref: '#/components/schemas/BPyd'
                    -   $ref: '#/components/schemas/CPyd'
            required:
            - sub_prop
            """,
        ]

    for fragment in expected_fragments:
        assert fragment.strip() in yaml


@pytest.mark.parametrize(
    "name,result",
    [
        ("Example[Cat]", "ExampleOfCat"),
        ("Union[A, B, C]", "UnionOfAAndBAndC"),
        ("List[Union[A, B, C]]", "ListOfUnionOfAAndBAndC"),
        ("Dict[str, int]", "DictOfstrAndint"),
    ],
)
def test_default_serializer_sanitize_name(name, result):
    serializer = DefaultSerializer()
    assert serializer.get_type_name_for_generic(name) == result
