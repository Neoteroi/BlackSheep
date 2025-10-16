"""
Test for issue #606: Ensure that the application can start and use OpenAPI Documentation
without optional dependencies.
"""

import sys

from dataclasses import dataclass

from blacksheep import Application, get
from blacksheep.server.openapi.v3 import OpenAPIHandler
from openapidocs.v3 import Info


# Ensure optional dependencies are not installed!
for pkg in ("cryptography", "jwt", "PyJWT"):
    try:
        __import__(pkg)
        print(f"ERROR: {pkg} is installed!")
        sys.exit(1)
    except ImportError:
        print(f"OK: {pkg} not installed.")


app = Application()

docs = OpenAPIHandler(info=Info(title="Example API", version="0.0.1"))
docs.bind_app(app)


@dataclass
class Foo:
    foo: str


@get("/foo")
async def get_foo() -> Foo:
    return Foo("Hello!")


print("OK... ✔️")
