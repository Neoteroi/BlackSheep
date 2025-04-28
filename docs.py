import json
from typing import List, Optional

from openapidocs.v3 import Info, OpenAPIElement
from pydantic import BaseModel, EmailStr, Field, HttpUrl

from blacksheep import Application, get
from blacksheep.server.openapi.v3 import OpenAPIHandler

app = Application()

docs = OpenAPIHandler(info=Info("Example API", version="0.0.1"))


class DirectSchema(OpenAPIElement):
    def __init__(self, obj):
        self.obj = obj

    def to_obj(self):
        return self.obj


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


# Example usage
user_schema = User.model_json_schema()
print(json.dumps(user_schema, indent=2))


@get("/user")
async def get_user() -> User: ...


@get("/users")
async def get_users() -> list[User]: ...


docs.set_type_schema(User, DirectSchema(User.model_json_schema()))
docs.set_type_schema(Address, DirectSchema(Address.model_json_schema()))

docs.bind_app(app)


if __name__ == "__main__":
    import asyncio

    asyncio.run(app.start())
