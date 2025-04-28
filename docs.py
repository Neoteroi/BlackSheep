from datetime import datetime
from typing import Annotated, List, Optional

from annotated_types import Gt
from openapidocs.v3 import Info
from pydantic import BaseModel, EmailStr, Field, HttpUrl
from pydantic.dataclasses import dataclass

from blacksheep import Application, get, post
from blacksheep.server.openapi.v3 import OpenAPIHandler


app = Application()

docs = OpenAPIHandler(info=Info("Example API", version="0.0.1"))


class Address(BaseModel):
    street: str
    city: str
    postal_code: str
    country: str = "USA"  # Default value


class User(BaseModel):
    id: int
    name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    website: Optional[HttpUrl] = None
    is_active: bool = True
    roles: List[str] = Field(default_factory=lambda: ["user"])
    address: Address


@dataclass
class OtherUser:
    id: int
    name: str = "John Doe"
    signup_ts: datetime | None = None


@get("/user")
async def get_user() -> User: ...


@get("/users")
async def get_users() -> list[User]: ...


@get("/users/{user_id}/addresses")
async def get_addresses(user_id: str) -> list[Address]: ...


@get("/pydantic-dataclass")
async def get_pydantic_dataclass_example() -> OtherUser: ...


@post("/pydantic-dataclass")
async def post(data: OtherUser): ...


type PositiveIntList = list[Annotated[int, Gt(0)]]


class Model(BaseModel):
    x: PositiveIntList
    y: PositiveIntList


@get("/test-model")
async def get_test_model(user_id: str) -> Model: ...


docs.bind_app(app)


if __name__ == "__main__":
    import asyncio

    asyncio.run(app.start())
