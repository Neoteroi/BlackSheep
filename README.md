[![Build](https://github.com/RobertoPrevato/BlackSheep/workflows/Main/badge.svg)](https://github.com/RobertoPrevato/BlackSheep/actions)
[![pypi](https://img.shields.io/pypi/v/BlackSheep.svg?color=blue)](https://pypi.org/project/BlackSheep/)
[![versions](https://img.shields.io/pypi/pyversions/blacksheep.svg)](https://github.com/robertoprevato/blacksheep)
[![codecov](https://codecov.io/gh/RobertoPrevato/BlackSheep/branch/master/graph/badge.svg?token=Nzi29L0Eg1)](https://codecov.io/gh/RobertoPrevato/BlackSheep)

# BlackSheep
BlackSheep is an asynchronous web framework to build event based, non-blocking Python web applications.
It is inspired by [Flask](https://palletsprojects.com/p/flask/), [ASP.NET Core](https://docs.microsoft.com/en-us/aspnet/core/), and the work by [Yury Selivanov](https://magic.io/blog/uvloop-blazing-fast-python-networking/).

<p align="left">
  <a href="#blacksheep"><img width="320" height="271" src="https://labeuwstacc.blob.core.windows.net/github/blacksheep.png" alt="Black Sheep"></a>
</p>

```bash
pip install blacksheep
```

---

```python
from datetime import datetime
from blacksheep.server import Application
from blacksheep.server.responses import text


app = Application()

@app.route("/")
async def home(request):
    return text(f"Hello, World! {datetime.utcnow().isoformat()}")

```

## Getting started
Use these project templates to get started:

* [BlackSheep MVC project template](https://github.com/RobertoPrevato/BlackSheepMVC)
* [BlackSheep empty project template](https://github.com/RobertoPrevato/BlackSheepEmptyProject)

## Requirements

BlackSheep belongs to the category of [ASGI](https://asgi.readthedocs.io/en/latest/) web frameworks, so it requires an ASGI HTTP server to run, such as [uvicorn](http://www.uvicorn.org/), [daphne](https://github.com/django/daphne/), or [hypercorn](https://pgjones.gitlab.io/hypercorn/). For example, to use it with uvicorn:

```bash
$ pip install uvicorn
```

To run an application like in the example above, use the methods provided by the ASGI HTTP Server:

```bash
# NB: if the BlackSheep app is defined in a file `server.py`

$ uvicorn server:app
```

To run for production, refer to the documentation of the chosen ASGI server (i.e. for [uvicorn](https://www.uvicorn.org/#running-with-gunicorn)).

## Automatic bindings and dependency injection
BlackSheep supports automatic binding of values for request handlers, by type annotation or by conventions. See [more here](https://github.com/RobertoPrevato/BlackSheep/wiki/Model-binding).

```python
from blacksheep.server.bindings import (
    FromJson,
    FromHeader,
    FromQuery,
    FromRoute,
    FromServices
)

@app.router.put("/:d")
async def example(
    a: FromQuery[List[str]],
    b: FromServices[Dog],
    c: FromJson[Cat],
    d: FromRoute[str],
    e: FromHeader[str]
):
    # a is read from query string parameters "a"
    # b is obtained from app services (DI)
    # c is read from request content parsed as JSON
    # d from the route parameter with matching name
    # e from a request header with name "e" or "E"
    ...


@app.router.get("/:culture_code/:area")
async def home(request, culture_code, area):
    # in this example, both parameters are obtained from routes with
    # matching names
    return text(f"Request for: {culture_code} {area}")


@app.router.get("/api/products")
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


@app.router.get("/api/products2")
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
It also supports dependency injection, provided by [rodi](https://github.com/RobertoPrevato/rodi),
a library from the same author, supporting `singleton`, `scoped`, and `transient` life style for activated services.

## Strategies to handle authentication and authorization
BlackSheep implements strategies to handle authentication and authorization,
using [GuardPost](https://github.com/RobertoPrevato/GuardPost), a library from
the same author.

```python
app.use_authentication()\
    .add(ExampleAuthenticationHandler())


app.use_authorization()\
    .add(AdminsPolicy())


@auth("admin")
@app.router.get("/")
async def only_for_admins():
    ...


@auth()
@app.router.get("/")
async def only_for_authenticated_users():
    ...
```

## Objectives
* Intelligible and easy to learn API, similar to those of many Python web frameworks
* Rich code API, based on Dependency Injection and inspired by ASP.NET Core
* Keep the core package minimal and focused, as much as possible, on features defined in HTTP and HTML standards
* Targeting stateless applications to be deployed in the cloud
* [High performance, see results from TechEmpower benchmarks (links in Wiki page)](https://github.com/RobertoPrevato/BlackSheep/wiki/Server-performance)

## Web framework features
* [ASGI compatibility](https://asgi.readthedocs.io/en/latest/)
* [Routing](https://github.com/RobertoPrevato/BlackSheep/wiki/Routing)
* [Request handlers can be defined as functions, or class methods](https://github.com/RobertoPrevato/BlackSheep/wiki/Defining-request-handlers)
* [Middlewares](https://github.com/RobertoPrevato/BlackSheep/wiki/Middlewares)
* [Built-in support for dependency injection](https://github.com/RobertoPrevato/BlackSheep/wiki/Dependency-injection)
* [Support for automatic binding of route and query parameters to request handlers methods calls](https://github.com/RobertoPrevato/BlackSheep/wiki/Handlers-normalization#route-parameters)
* [Strategy to handle exceptions](https://github.com/RobertoPrevato/BlackSheep/wiki/Exceptions-handling)
* [Strategy to handle authentication and authorization](https://github.com/RobertoPrevato/BlackSheep/wiki/Authentication-and-authorization-strategies)
* [Handlers normalization](https://github.com/RobertoPrevato/BlackSheep/wiki/Handlers-normalization)
* [Chunked encoding](https://github.com/RobertoPrevato/BlackSheep/wiki/Chunked-encoding) through generators (yield syntax)
* [Serving static files](https://github.com/RobertoPrevato/BlackSheep/wiki/Serving-static-files)
* [Integration with Jinja2](https://github.com/RobertoPrevato/BlackSheep/wiki/Jinja2)
* [Support for serving SPAs that use HTML5 History API for client side routing](https://github.com/RobertoPrevato/BlackSheep/wiki/How-to-serve-SPAs-that-use-HTML5-History-API)
* [Support for automatic generation of OpenAPI Documentation](https://github.com/RobertoPrevato/BlackSheep/wiki/OpenAPI)

## Client features
* [HTTP connection pooling](https://github.com/RobertoPrevato/BlackSheep/wiki/Connection-pooling)
* User friendly [handling of SSL contexts](https://github.com/RobertoPrevato/BlackSheep/wiki/Client-handling-SSL-contexts) (safe by default)
* Support for [client side middlewares](https://github.com/RobertoPrevato/BlackSheep/wiki/Client-middlewares), enabling clean source code and separation of concerns (logging of different kinds, handling of cookies, etc.)
* Automatic handling of redirects (can be disabled, validates circular redirects and maximum number of redirects - redirects to URN are simply returned to code using the client)
* Automatic handling of cookies (can be disabled, `Set-Cookie` and `Cookie` headers)

**Example:**
```python
import asyncio
from blacksheep.client import ClientSession


async def client_example(loop):
    async with ClientSession() as client:
        response = await client.get("https://docs.python.org/3/")

        assert response is not None
        text = await response.text()
        print(text)


loop = asyncio.get_event_loop()
loop.run_until_complete(client_example(loop))

```

## Supported platforms and runtimes
The following Python versions are supported and tested by [validation pipeline](./azure-pipelines.yml),
or during development:
* Python 3.7 (cpython)
* Python 3.8 (cpython)
* Python 3.9 (cpython)

The following platforms are supported and tested by [validation pipeline](./azure-pipelines.yml):
* Ubuntu 18.04
* Windows 10

## Documentation
Please refer to the [project Wiki](https://github.com/RobertoPrevato/BlackSheep/wiki).
