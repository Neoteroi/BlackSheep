[![Build](https://github.com/Neoteroi/BlackSheep/workflows/Main/badge.svg)](https://github.com/Neoteroi/BlackSheep/actions)
[![pypi](https://img.shields.io/pypi/v/BlackSheep.svg?color=blue)](https://pypi.org/project/BlackSheep/)
[![versions](https://img.shields.io/pypi/pyversions/blacksheep.svg)](https://github.com/robertoprevato/blacksheep)
[![license](https://img.shields.io/github/license/Neoteroi/blacksheep.svg)](https://github.com/Neoteroi/blacksheep/blob/main/LICENSE) [![Join the chat at https://gitter.im/Neoteroi/BlackSheep](https://badges.gitter.im/Neoteroi/BlackSheep.svg)](https://gitter.im/Neoteroi/BlackSheep?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge) [![documentation](https://img.shields.io/badge/📖-docs-purple)](https://www.neoteroi.dev/blacksheep/)

# BlackSheep

BlackSheep is an asynchronous web framework to build event based web
applications with Python. It is inspired by
[Flask](https://palletsprojects.com/p/flask/), [ASP.NET
Core](https://docs.microsoft.com/en-us/aspnet/core/), and the work by [Yury
Selivanov](https://magic.io/blog/uvloop-blazing-fast-python-networking/).

<p align="left">
  <a href="#blacksheep"><img width="320" height="271" src="https://www.neoteroi.dev/blacksheep/img/blacksheep.png" alt="Black Sheep"></a>
</p>

```bash
pip install blacksheep
```

---

```python
from datetime import datetime

from blacksheep import Application, get


app = Application()

@get("/")
async def home():
    return f"Hello, World! {datetime.utcnow().isoformat()}"

```

## Getting started using the CLI ✨

BlackSheep offers a CLI to bootstrap new projects rapidly.
To try it, first install the `blacksheep-cli` package:

```bash
pip install blacksheep-cli
```

Then use the `blacksheep create` command to bootstrap a project
using one of the supported templates.

![blacksheep create command](https://gist.githubusercontent.com/RobertoPrevato/38a0598b515a2f7257c614938843b99b/raw/67d15ba337de94c2f50d980a7b8924a747259254/blacksheep-create-demo.gif)

The CLI includes a help, and supports custom templates, using the
same sources supported by `Cookiecutter`.

## Dependencies

Before version `2.3.1`, BlackSheep only supported running with `CPython` and
always depended on `httptools`. Starting with version `2.3.1`, the framework
supports running on [`PyPy`](https://pypy.org/) and makes `httptools` an
optional dependency. The BlackSheep HTTP Client requires either `httptools`
(for CPython) or `h11` (for PyPy).

For slightly better performance in `URL` parsing when running on `CPython`,
it is recommended to install `httptools`.

> [!TIP]
>
> The best performance can be achieved using `PyPy` runtime, and
> [`Socketify`](https://docs.socketify.dev/cli.html) or [`Granian`](https://github.com/emmett-framework/granian), (see
> [#539](https://github.com/Neoteroi/BlackSheep/issues/539) for more information).

## Getting started with the documentation

The documentation offers getting started tutorials:
* [Getting started:
  basics](https://www.neoteroi.dev/blacksheep/getting-started/)
* [Getting started: the MVC project
  template](https://www.neoteroi.dev/blacksheep/mvc-project-template/)

These project templates can be used to start new applications faster:

* [MVC project
  template](https://github.com/Neoteroi/BlackSheepMVC)
* [Empty project
  template](https://github.com/Neoteroi/BlackSheepEmptyProject)

## Requirements

[Python](https://www.python.org): any version listed in the project's
classifiers. The current list is:

[![versions](https://img.shields.io/pypi/pyversions/blacksheep.svg)](https://github.com/robertoprevato/blacksheep)

> [!TIP]
>
> Starting from version `2.3.1`, BlackSheep supports [PyPy](https://pypy.org/), too (`PyPy 3.11`).
> Previous versions of the framework supported only [CPython](https://github.com/python/cpython).

BlackSheep belongs to the category of
[ASGI](https://asgi.readthedocs.io/en/latest/) web frameworks, so it requires
an ASGI HTTP server to run, such as [uvicorn](https://www.uvicorn.org/),
[hypercorn](https://pgjones.gitlab.io/hypercorn/) or
[granian](https://github.com/emmett-framework/granian).
For example, to use it with uvicorn:

```bash
$ pip install uvicorn
```

To run an application like in the example above, use the methods provided by
the ASGI HTTP Server:

```bash
# if the BlackSheep app is defined in a file `server.py`

$ uvicorn server:app
```

To run for production, refer to the documentation of the chosen ASGI server
(i.e. for [uvicorn](https://www.uvicorn.org/#running-with-gunicorn)).

## Automatic bindings and dependency injection

BlackSheep supports automatic binding of values for request handlers, by type
annotation or by conventions. See [more
here](https://www.neoteroi.dev/blacksheep/requests/).

```python
from dataclasses import dataclass

from blacksheep import Application, FromJSON, FromQuery, get, post


app = Application()


@dataclass
class CreateCatInput:
    name: str


@post("/api/cats")
async def example(data: FromJSON[CreateCatInput]):
    # in this example, data is bound automatically reading the JSON
    # payload and creating an instance of `CreateCatInput`
    ...


@get("/:culture_code/:area")
async def home(culture_code, area):
    # in this example, both parameters are obtained from routes with
    # matching names
    return f"Request for: {culture_code} {area}"


@get("/api/products")
def get_products(
    page: int = 1,
    size: int = 30,
    search: str = "",
):
    # this example illustrates support for implicit query parameters with
    # default values
    # since the source of page, size, and search is not specified and no
    # route parameter matches their name, they are obtained from query string
    ...


@get("/api/products2")
def get_products2(
    page: FromQuery[int] = FromQuery(1),
    size: FromQuery[int] = FromQuery(30),
    search: FromQuery[str] = FromQuery(""),
):
    # this example illustrates support for explicit query parameters with
    # default values
    # in this case, parameters are explicitly read from query string
    ...

```

It also supports [dependency
injection](https://www.neoteroi.dev/blacksheep/dependency-injection/), a
feature that provides a consistent and clean way to use dependencies in request
handlers.

## Generation of OpenAPI Documentation

[Generation of OpenAPI Documentation](https://www.neoteroi.dev/blacksheep/openapi/).

## Strategies to handle authentication and authorization

BlackSheep implements strategies to handle authentication and authorization.
These features are documented here:

* [Authentication](https://www.neoteroi.dev/blacksheep/authentication/)
* [Authorization](https://www.neoteroi.dev/blacksheep/authorization/)

```python
app.use_authentication()\
    .add(ExampleAuthenticationHandler())


app.use_authorization()\
    .add(AdminsPolicy())


@auth("admin")
@get("/")
async def only_for_admins():
    ...


@auth()
@get("/")
async def only_for_authenticated_users():
    ...
```

BlackSheep provides:

* [Built-in support for OpenID Connect authentication](https://www.neoteroi.dev/blacksheep/authentication/#oidc)
* [Built-in support for JWT Bearer authentication](https://www.neoteroi.dev/blacksheep/authentication/#jwt-bearer)

Meaning that it is easy to integrate with services such as:
* [Auth0](https://auth0.com)
* [Azure Active Directory](https://azure.microsoft.com/en-us/services/active-directory/)
* [Azure Active Directory B2C](https://docs.microsoft.com/en-us/azure/active-directory-b2c/overview)
* [Okta](https://www.okta.com)

Refer to the documentation and to [BlackSheep-Examples](https://github.com/Neoteroi/BlackSheep-Examples)
for more details and examples.

## Web framework features

* [ASGI compatibility](https://www.neoteroi.dev/blacksheep/asgi/)
* [Routing](https://www.neoteroi.dev/blacksheep/routing/)
* Request handlers can be [defined as
  functions](https://www.neoteroi.dev/blacksheep/request-handlers/), or [class
  methods](https://www.neoteroi.dev/blacksheep/controllers/)
* [Middlewares](https://www.neoteroi.dev/blacksheep/middlewares/)
* [WebSocket](https://www.neoteroi.dev/blacksheep/websocket/)
* [Server-Sent Events (SSE)](https://www.neoteroi.dev/blacksheep/server-sent-events/)
* [Built-in support for dependency
  injection](https://www.neoteroi.dev/blacksheep/dependency-injection/)
* [Support for automatic binding of route and query parameters to request
  handlers methods
  calls](https://www.neoteroi.dev/blacksheep/getting-started/#handling-route-parameters)
* [Strategy to handle
  exceptions](https://www.neoteroi.dev/blacksheep/application/#configuring-exceptions-handlers)
* [Strategy to handle authentication and
  authorization](https://www.neoteroi.dev/blacksheep/authentication/)
* [Built-in support for OpenID Connect authentication using OIDC
  discovery](https://www.neoteroi.dev/blacksheep/authentication/#oidc)
* [Built-in support for JWT Bearer authentication using OIDC discovery and
  other sources of
  JWKS](https://www.neoteroi.dev/blacksheep/authentication/#jwt-bearer)
* [Handlers
  normalization](https://www.neoteroi.dev/blacksheep/request-handlers/)
* [Serving static
  files](https://www.neoteroi.dev/blacksheep/static-files/)
* [Integration with
  Jinja2](https://www.neoteroi.dev/blacksheep/templating/)
* [Support for serving SPAs that use HTML5 History API for client side
  routing](https://www.neoteroi.dev/blacksheep/static-files/#how-to-serve-spas-that-use-html5-history-api)
* [Support for automatic generation of OpenAPI
  Documentation](https://www.neoteroi.dev/blacksheep/openapi/)
* [Strategy to handle CORS settings](https://www.neoteroi.dev/blacksheep/cors/)
* [Sessions](https://www.neoteroi.dev/blacksheep/sessions/)
* Support for automatic binding of `dataclasses` and
  [`Pydantic`](https://pydantic-docs.helpmanual.io) models to handle the
  request body payload expected by request handlers
* [`TestClient` class to simplify testing of applications](https://www.neoteroi.dev/blacksheep/testing/)
* [Anti Forgery validation](https://www.neoteroi.dev/blacksheep/anti-request-forgery) to protect against Cross-Site Request Forgery (XSRF/CSRF) attacks

## Client features

BlackSheep includes an HTTP Client.

**Example:**
```python
import asyncio

from blacksheep.client import ClientSession


async def client_example():
    async with ClientSession() as client:
        response = await client.get("https://docs.python.org/3/")
        text = await response.text()
        print(text)


asyncio.run(client_example())
```

> [!IMPORTANT]
>
> Starting from version `2.3.1`, BlackSheep supports [PyPy](https://pypy.org/),
> too (`PyPy 3.11`). For this reason, using the client requires an additional
> dependency: `httptools` if using CPython, `h11` if using `PyPy`. This affects
> only the `blacksheep.client` namespace.

## Supported platforms and runtimes

* Python: all versions included in the [build matrix](.github/workflows/main.yml).
* CPython and PyPy.
* Ubuntu.
* Windows 10.
* macOS.

## Documentation

Please refer to the [documentation website](https://www.neoteroi.dev/blacksheep/).

## Communication

[BlackSheep community in Gitter](https://gitter.im/Neoteroi/BlackSheep).

## Branches

The _main_ branch contains the currently developed version, which is version 2. The _v1_ branch contains version 1 of the web framework, for bugs fixes
and maintenance.
