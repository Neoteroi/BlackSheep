"""
Test for issue #606: Ensure that the application can start and use OpenAPI Documentation
without optional dependencies.
"""

from dataclasses import dataclass

from blacksheep import Application, get
from blacksheep.server.openapi.v3 import OpenAPIHandler
from openapidocs.v3 import Info

app = Application()

docs = OpenAPIHandler(info=Info(title="Example API", version="0.0.1"))
docs.bind_app(app)


@dataclass
class Foo:
    foo: str


@get("/foo")
async def get_foo() -> Foo:
    return Foo("Hello!")
