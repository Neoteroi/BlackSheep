"""
uvicorn apitest:app --port 44777

curl http://127.0.0.1:44777 -H "X-API-Key: Foo"
"""

from dataclasses import dataclass

from openapidocs.v3 import Info

from blacksheep import Application, get
from blacksheep.server.authentication.apikey import APIKey, APIKeyAuthentication
from blacksheep.server.authorization import auth
from blacksheep.server.openapi.v3 import OpenAPIHandler

app = Application()


app.use_authentication().add(
    APIKeyAuthentication(
        APIKey(
            name="X-API-KEY",
            secret="my-secret-1243",
            roles=["user"],
        )
    )
)

app.use_authorization()


docs = OpenAPIHandler(info=Info(title="Example API", version="0.0.1"))
docs.bind_app(app)


@dataclass
class Foo:
    foo: str


@auth()
@get("/")
async def get_foo() -> Foo:
    return Foo("Hello!")


@auth()
@get("/claims")
async def get_claims(request):
    return request.user.claims


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, port=44777)
