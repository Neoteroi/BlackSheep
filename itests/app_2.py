import json
from base64 import urlsafe_b64decode
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from http import HTTPStatus
from typing import List, Optional, Set
from uuid import UUID

import uvicorn
from dateutil.parser import parse as dateutil_parse
from guardpost import AuthorizationContext, Identity
from guardpost.common import AuthenticatedRequirement
from openapidocs.v3 import Discriminator, Info, MediaType, Operation
from openapidocs.v3 import Response as ResponseDoc
from openapidocs.v3 import Schema
from pydantic import BaseModel

from blacksheep import Response, TextContent, WebSocket
from blacksheep.server import Application
from blacksheep.server.authentication import AuthenticationHandler
from blacksheep.server.authorization import Policy, Requirement, auth
from blacksheep.server.bindings import (
    FromCookie,
    FromForm,
    FromHeader,
    FromJSON,
    FromQuery,
    FromServices,
)
from blacksheep.server.compression import use_gzip_compression
from blacksheep.server.controllers import APIController
from blacksheep.server.openapi.common import (
    ContentInfo,
    EndpointDocs,
    HeaderInfo,
    ParameterInfo,
    ParameterSource,
    RequestBodyInfo,
    ResponseExample,
    ResponseInfo,
)
from blacksheep.server.openapi.ui import ReDocUIProvider
from blacksheep.server.openapi.v3 import OpenAPIHandler
from blacksheep.server.responses import text
from blacksheep.server.routing import RoutesRegistry
from itests.utils import CrashTest

app_2 = Application()

use_gzip_compression(app_2)

controllers_router = RoutesRegistry()
app_2.controllers_router = controllers_router

get = controllers_router.get
post = controllers_router.post
delete = controllers_router.delete


# OpenAPI v3 configuration:
docs = OpenAPIHandler(info=Info(title="Cats API", version="0.0.1"))
docs.ui_providers.append(ReDocUIProvider())

# include only endpoints whose path starts with "/api/"
docs.include = lambda path, _: path.startswith("/api/")
docs.bind_app(app_2)


class HandledException(Exception):
    def __init__(self):
        super().__init__("Example exception")


async def handle_test_exception(app, request, http_exception):
    return Response(200, content=TextContent("Fake exception, to test handlers"))


app_2.exceptions_handlers[HandledException] = handle_test_exception


@dataclass
class SomeService:
    pass


app_2.services.add_transient(SomeService)


class AdminRequirement(Requirement):
    def handle(self, context: AuthorizationContext):
        identity = context.identity

        if identity is not None and identity.claims.get("role") == "admin":
            context.succeed(self)


class AdminsPolicy(Policy):
    def __init__(self):
        super().__init__("admin", AdminRequirement())


class MockAuthHandler(AuthenticationHandler):
    def __init__(self):
        pass

    async def authenticate(self, context):
        header_value = context.get_first_header(b"Authorization")
        if header_value:
            data = json.loads(urlsafe_b64decode(header_value).decode("utf8"))
            context.user = Identity(data, "FAKE")
        else:
            context.user = None
        return context.user


app_2.use_authentication().add(MockAuthHandler())


app_2.use_authorization().add(AdminsPolicy()).add(
    Policy("authenticated", AuthenticatedRequirement())
)


@docs(responses={200: "Example"})
@app_2.router.get("/api/dogs/bark")
def bark(example: FromCookie[str], example_header: FromHeader[str]):
    return text("Bau Bau")


@app_2.router.get("/api/dogs/sleep/*")
def not_documented():
    return text("Ignored because catch-all")


@auth("admin")
@app_2.router.get("/only-for-admins")
async def only_for_admins():
    return None


@auth("admin")
@app_2.router.ws("/websocket-echo-text-auth")
async def echo_text_admin_users(websocket: WebSocket):
    await websocket.accept()

    while True:
        msg = await websocket.receive_text()
        await websocket.send_text(msg)


@app_2.router.ws("/websocket-error-before-accept")
async def echo_text_http_exp(websocket: WebSocket):
    raise RuntimeError("Error before accept")


@app_2.router.ws("/websocket-server-error")
async def websocket_server_error(websocket: WebSocket):
    await websocket.accept()
    raise RuntimeError("Server error")


@auth("authenticated")
@app_2.router.get("/only-for-authenticated-users")
async def only_for_authenticated_users():
    return None


@app_2.router.route("/crash")
async def crash():
    raise CrashTest()


@app_2.router.route("/handled-crash")
async def handled_crash():
    raise HandledException()


class CatType(Enum):
    EUROPEAN = "european"
    PERSIAN = "persian"


@dataclass
class Cat:
    id: UUID
    name: str
    active: bool
    type: CatType
    creation_time: datetime


@dataclass
class HttpError:
    status: int
    message: str
    code: str


@dataclass
class CreateCatInput:
    name: str
    active: bool
    type: CatType


@dataclass
class CreateCatOutput:
    id: UUID


class PydanticChild(BaseModel):
    foo: bool


class PydanticExample(BaseModel):
    name: str
    active: bool
    foo: float
    birthdate: date
    type: CatType
    items: List[PydanticChild]


@dataclass
class Example:
    name: Optional[str]
    active: Optional[bool]


@dataclass
class Example2:
    friend: "Cat"


create_cat_docs = EndpointDocs(
    request_body=RequestBodyInfo(
        description="Example description etc. etc.",
        examples={
            "fat_cat": CreateCatInput(
                name="Fatty",
                active=False,
                type=CatType.EUROPEAN,
            ),
            "thin_cat": CreateCatInput(
                name="Thinny",
                active=False,
                type=CatType.PERSIAN,
            ),
        },
    ),
    responses={
        201: ResponseInfo(
            "The cat has been created",
            headers={"Location": HeaderInfo(str, "URL to the new created object")},
            content=[
                ContentInfo(
                    CreateCatOutput,
                    examples=[
                        ResponseExample(
                            CreateCatOutput(
                                UUID("7d6299fa-77d4-4fb0-825d-3c0c7ba759d5")
                            ),
                            description="Something something",
                        ),
                        CreateCatOutput(UUID("8f885fa9-e92f-47aa-a296-207e8105ad9b")),
                        CreateCatOutput(UUID("7e530116-5bd6-40d3-b539-9966ab066720")),
                    ],
                ),
            ],
        ),
        400: ResponseInfo(
            "Bad request",
            content=[
                ContentInfo(
                    HttpError,
                    examples=[
                        HttpError(
                            404,
                            "Bad request because something something",
                            "DUPLICATE_CAT",
                        )
                    ],
                )
            ],
        ),
    },
)


@dataclass
class CatsList:
    items: List[Cat]
    total: int


class PetType(Enum):
    CAT = "cat"
    DOG = "dog"


@dataclass
class Animal:
    beauty: float


@dataclass
class Pet(Animal):
    name: str
    type: PetType


@dataclass
class CatPet(Pet):
    laziness: float


@dataclass
class DogPet(Pet):
    loyalty: float


class AnimalModel(BaseModel):
    beauty: float


class PetModel(AnimalModel):
    name: str
    type: PetType


class DogPetModel(PetModel):
    loyalty: float


class CatPetModel(PetModel):
    laziness: float


@dataclass
class Foo:
    id: UUID
    name: str
    cool: float


@dataclass
class UpdateFooInput:
    name: str
    cool: float
    etag: Optional[str]


@dataclass
class FooList:
    items: List[Foo]
    total: int


def on_polymorph_example_docs_created(
    docs: OpenAPIHandler, operation: Operation
) -> None:
    docs.register_schema_for_type(Pet)
    pet_schema = docs.components.schemas["Pet"]
    assert isinstance(pet_schema, Schema)
    pet_schema.discriminator = Discriminator("type", {"cat": "CatPet", "dog": "DogPet"})

    cat_ref = docs.register_schema_for_type(CatPet)
    dog_ref = docs.register_schema_for_type(DogPet)

    operation.responses["200"] = ResponseDoc(
        "Polymorph example",
        content={
            "application/json": MediaType(schema=Schema(any_of=[cat_ref, dog_ref]))
        },
    )


def on_polymorph_example_docs_created_pydantic(
    docs: OpenAPIHandler, operation: Operation
) -> None:
    docs.register_schema_for_type(PetModel)
    pet_schema = docs.components.schemas["Pet"]
    assert isinstance(pet_schema, Schema)
    pet_schema.discriminator = Discriminator("type", {"cat": "CatPet", "dog": "DogPet"})

    cat_ref = docs.register_schema_for_type(CatPetModel)
    dog_ref = docs.register_schema_for_type(DogPetModel)

    operation.responses["200"] = ResponseDoc(
        "Polymorph example",
        content={
            "application/json": MediaType(schema=Schema(any_of=[cat_ref, dog_ref]))
        },
    )


class Cats(APIController):
    @get()
    @docs(
        parameters={
            "page": ParameterInfo(description="Page number"),
        },
        responses={
            HTTPStatus.OK: ResponseInfo(
                "A paginated set of Cats",
                content=[
                    ContentInfo(
                        CatsList,
                        examples=[
                            CatsList(
                                [
                                    Cat(
                                        id=UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
                                        name="Foo",
                                        active=True,
                                        type=CatType.EUROPEAN,
                                        creation_time=dateutil_parse(
                                            "2020-10-25T19:39:31.751652"
                                        ),
                                    ),
                                    Cat(
                                        id=UUID("f212cabf-987c-48e6-8cad-71d1c041209a"),
                                        name="Frufru",
                                        active=True,
                                        type=CatType.PERSIAN,
                                        creation_time=dateutil_parse(
                                            "2020-10-25T19:39:31.751652"
                                        ),
                                    ),
                                ],
                                1230,
                            )
                        ],
                    )
                ],
            ),
            "400": "Bad Request",
        },
    )
    def get_cats(
        self,
        page: FromQuery[int] = FromQuery(1),
        page_size: FromQuery[int] = FromQuery(30),
        search: FromQuery[str] = FromQuery(""),
    ) -> Response:
        """
        Returns a list of paginated cats.

        :param int page: Page number
        :param int page_size: Number of items per page
        :param str search: Optional search filter
        """

    @get("foos")
    def get_foos() -> FooList: ...

    @get("cats2")
    def get_cats_alt2(
        self,
        page: FromQuery[int] = FromQuery(1),
        page_size: FromQuery[int] = FromQuery(30),
        search: FromQuery[str] = FromQuery(""),
    ) -> CatsList:
        """
        Alternative way to have the response type for status 200 documented.

        Parameters
        ----------
        page : int
            Page number.
        page_size : int
            Number of items per page.
        search : str
            Optional search filter.
        """
        return CatsList(
            [
                Cat(
                    id=UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
                    name="Foo",
                    active=True,
                    type=CatType.EUROPEAN,
                    creation_time=dateutil_parse("2020-10-25T19:39:31.751652"),
                ),
                Cat(
                    id=UUID("f212cabf-987c-48e6-8cad-71d1c041209a"),
                    name="Frufru",
                    active=True,
                    type=CatType.PERSIAN,
                    creation_time=dateutil_parse("2020-10-25T19:39:31.751652"),
                ),
            ],
            1230,
        )

    @docs(
        parameters={
            "page": ParameterInfo(
                "Optional page number (default 1)",
                source=ParameterSource.QUERY,
                value_type=int,
                required=False,
            ),
            "page_size": ParameterInfo(
                "Optional page size (default 30)",
                source=ParameterSource.QUERY,
                value_type=int,
                required=False,
            ),
            "search": ParameterInfo(
                "Optional search filter",
                source=ParameterSource.QUERY,
                value_type=str,
                required=False,
            ),
        }
    )
    @get("cats3")
    def get_cats_alt3(self, request) -> CatsList:
        """
        Note: in this scenario, query parameters can be read from the request object
        """
        ...

    @get("cats4")
    def get_cats_alt4(self, request) -> CatsList:
        """
        Returns a paginated set of cats.

        @param int or None page: Optional page number (default 1).
        @param int or None page_size: Optional page size (default 30).
        @param str or None search: Optional search filter.
        @rtype:   CatsList
        @return:  a paginated set of cats.
        """
        ...

    @post("/foo")
    async def update_foo(self, foo_id: UUID, data: UpdateFooInput) -> Foo:
        """
        Updates a foo by id.

        @param foo_id: the id of the album to update.
        @param data: input for the update operation.
        """

    @docs(
        request_body=RequestBodyInfo(
            examples={
                "basic": UpdateFooInput(
                    name="Foo 2",
                    cool=9000,
                    etag="aaaaaaaa",
                )
            },
        ),
    )
    @post("/foo2/{foo_id}")
    async def update_foo2(
        self,
        foo_id: UUID,
        data: UpdateFooInput,
        some_service: FromServices[SomeService],
    ) -> Foo:
        """
        Updates a foo by id.

        @param foo_id: the id of the foo to update.
        @param data: input for the update operation.
        @param some_service: a service injected by dependency injection and used for
               some reason.
        """

    @docs.ignore()
    @get("/ignored")
    def secret_api(self): ...

    @docs.summary("Some deprecated API")
    @docs.deprecated()
    @docs.tags("Cats", "Deprecated")
    @get("/deprecated")
    def deprecated_api(self):
        """
        This endpoint is deprecated.
        """

    @docs(
        summary="Gets a cat by id",
        description="""A sample API that uses a petstore as an
          example to demonstrate features in the OpenAPI 3 specification""",
        responses={
            200: ResponseInfo(
                "A cat",
                content=[
                    ContentInfo(
                        Cat,
                        examples=[
                            ResponseExample(
                                Cat(
                                    id=UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
                                    name="Foo",
                                    active=True,
                                    type=CatType.EUROPEAN,
                                    creation_time=dateutil_parse(
                                        "2020-10-25T19:39:31.751652"
                                    ),
                                )
                            )
                        ],
                    )
                ],
            ),
            404: "Cat not found",
        },
    )
    @get(":cat_id")
    def get_cat(self, cat_id: str) -> Response:
        """
        Gets a cat by id.
        """

    @post()
    @docs(create_cat_docs)
    def create_cat(self, input: FromJSON[CreateCatInput]) -> Response:
        """
        Creates a new cat.
        """

    @post("/variant")
    @docs(create_cat_docs)
    def post_form(self, input: FromForm[CreateCatInput]) -> Response:
        """
        ...
        """

    @docs(
        responses={
            204: "Cat deleted successfully",
        },
    )
    @delete(":cat_id")
    def delete_cat(self, cat_id: str) -> Response:
        """
        Deletes a cat by id.

        Lorem ipsum dolor sit amet.
        """

    @post("magic")
    def magic_cat(self, cat: PydanticExample, foo: Optional[bool]) -> Response:
        """
        Creates a magic cat
        """

    @post("magic2")
    def magic_cat2(self, cat: PydanticExample) -> Response:
        """
        Creates a magic cat
        """

    @post("magic3")
    def magic_cat3(self, example: Example) -> Response:
        """
        Creates a magic cat
        """

    @post("forward_ref")
    def magic_cat4(self, example: Example2) -> Response: ...

    @post("poor-use-of-list-annotation")
    def magic_cat5(self, example: list) -> Response: ...

    @post("poor-use-of-set-annotation2")
    def magic_cat6(self, example: Set) -> Response: ...

    @post("/polymorph-example")
    @docs(on_created=on_polymorph_example_docs_created)
    def polymorph_example(self) -> Response: ...

    @post("/polymorph-example-pydantic")
    @docs(on_created=on_polymorph_example_docs_created_pydantic)
    def polymorph_example_pydantic(self) -> Response: ...


if __name__ == "__main__":
    uvicorn.run(app_2, host="127.0.0.1", port=44566, log_level="debug")
