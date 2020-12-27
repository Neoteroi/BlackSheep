[![Build](https://github.com/RobertoPrevato/BlackSheep/workflows/Main/badge.svg)](https://github.com/RobertoPrevato/BlackSheep/actions)
[![pypi](https://img.shields.io/pypi/v/BlackSheep.svg?color=blue)](https://pypi.org/project/BlackSheep/)
[![versions](https://img.shields.io/pypi/pyversions/blacksheep.svg)](https://github.com/robertoprevato/blacksheep)
[![codecov](https://codecov.io/gh/RobertoPrevato/BlackSheep/branch/master/graph/badge.svg?token=Nzi29L0Eg1)](https://codecov.io/gh/RobertoPrevato/BlackSheep)
[![license](https://img.shields.io/github/license/RobertoPrevato/blacksheep.svg)](https://github.com/RobertoPrevato/blacksheep/blob/master/LICENSE)

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
from blacksheep.server import Application
from blacksheep.server.responses import text


app = Application()

@app.route("/")
async def home(request):
    return text(f"Hello, World! {datetime.utcnow().isoformat()}")

```

## Getting started
The documentation offers getting started tutorials:
* [Getting started:
  basics](https://www.neoteroi.dev/blacksheep/getting-started/)
* [Getting started: the MVC project
  template](https://www.neoteroi.dev/blacksheep/mvc-project-template/)

These project templates can be used to start new applications faster:

* [BlackSheep MVC project
  template](https://github.com/RobertoPrevato/BlackSheepMVC)
* [BlackSheep empty project
  template](https://github.com/RobertoPrevato/BlackSheepEmptyProject)

## Requirements

[Python](https://www.python.org) version **3.7**, **3.8**, or **3.9**.

BlackSheep belongs to the category of
[ASGI](https://asgi.readthedocs.io/en/latest/) web frameworks, so it requires
an ASGI HTTP server to run, such as [uvicorn](http://www.uvicorn.org/),
[daphne](https://github.com/django/daphne/), or
[hypercorn](https://pgjones.gitlab.io/hypercorn/). For example, to use it with
uvicorn:

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
BlackSheep supports automatic binding of values for request handlers by type
annotation or by conventions. See [more
here](https://www.neoteroi.dev/blacksheep/requests/).

```python
from dataclasses import dataclass

from blacksheep.server.bindings import FromJson


@dataclass
class CreateCatInput:
    name: str


@app.router.post("/api/cats")
async def example(data: FromJson[CreateCatInput]):
    # in this example, data is bound automatically reading the JSON
    # payload and creating an instance of `CreateCatInput`
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
@app.router.get("/")
async def only_for_admins():
    ...


@auth()
@app.router.get("/")
async def only_for_authenticated_users():
    ...
```

## Web framework features
* [ASGI compatibility](https://www.neoteroi.dev/blacksheep/asgi/)
* [Routing](https://www.neoteroi.dev/blacksheep/routing/)
* Request handlers can be [defined as
  functions](https://www.neoteroi.dev/blacksheep/request-handlers/), or [class
  methods](https://www.neoteroi.dev/blacksheep/controllers/)
* [Middlewares](https://www.neoteroi.dev/blacksheep/middlewares/)
* [Built-in support for dependency
  injection](https://www.neoteroi.dev/blacksheep/dependency-injection/)
* [Support for automatic binding of route and query parameters to request
  handlers methods
  calls](https://www.neoteroi.dev/blacksheep/getting-started/#handling-route-parameters)
* [Strategy to handle
  exceptions](https://www.neoteroi.dev/blacksheep/application/#configuring-exceptions-handlers)
* [Strategy to handle authentication and
  authorization](https://www.neoteroi.dev/blacksheep/authentication/)
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
## Client features
BlackSheep includes an HTTP Client.

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
* Python 3.7 (cpython)
* Python 3.8 (cpython)
* Python 3.9 (cpython)
* Ubuntu 18.04
* Windows 10
* macOS

## Documentation
Please refer to the [documentation website](https://www.neoteroi.dev/blacksheep/).
