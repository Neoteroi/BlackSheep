"""
EXAMPLE. REMOVE BEFORE MERGING.

uvicorn apitest:app --port 44777

curl http://127.0.0.1:44777 -H "X-API-Key: Foo"
"""

from dataclasses import dataclass

from essentials.secrets import Secret
from openapidocs.v3 import Info

from blacksheep import Application, get
from blacksheep.server.authentication.apikey import APIKey, APIKeyAuthentication
from blacksheep.server.authentication.basic import BasicAuthentication, BasicCredentials
from blacksheep.server.authorization import auth
from blacksheep.server.openapi.v3 import OpenAPIHandler

app = Application()


admin_credentials = BasicCredentials(
    username="admin",
    password=Secret("$ADMIN_PASSWORD"),
    roles=["admin"],
)

print(admin_credentials.to_header_value())

app.use_authentication().add(
    APIKeyAuthentication(
        APIKey(
            secret=Secret("$API_SECRET"),
            roles=["user"],
        ),
        param_name="X-API-Key",
    )
).add(BasicAuthentication(admin_credentials))

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


@auth(roles=["admin"])
@get("/for-admins")
async def for_admins_only(request):
    return request.user.claims


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, port=44777)
