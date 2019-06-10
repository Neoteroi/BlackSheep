[![Build status](https://dev.azure.com/robertoprevato/BlackSheep/_apis/build/status/BlackSheep-CI)](https://dev.azure.com/robertoprevato/BlackSheep/_build/latest?definitionId=7) [![pypi](https://vsrm.dev.azure.com/robertoprevato/_apis/public/Release/badge/4c3c4d06-612f-4802-9400-7101b0b43a73/1/2)](https://pypi.org/project/BlackSheep/)

# BlackSheep
Fast HTTP Server/Client microframework for Python asyncio, using [Cython](https://cython.org), 
[`uvloop`](https://magic.io/blog/uvloop-blazing-fast-python-networking/), and 
[`httptools`](https://github.com/MagicStack/httptools). 

<p align="left">
  <a href="#blacksheep"><img width="320" height="271" src="https://raw.githubusercontent.com/RobertoPrevato/BlackSheep/master/black-sheep.svg?sanitize=true" alt="Black Sheep"></a>
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

@app.route('/')
async def home(request):
    return text(f'Hello, World! {datetime.utcnow().isoformat()}')

app.start()
```

## Automatic bindings and dependency injection
BlackSheep supports automatic binding of values for request handlers, by type annotation or by conventions. See [more here](https://github.com/RobertoPrevato/BlackSheep/wiki/Model-binding).
```python
from blacksheep.server.bindings import (FromJson,
                                        FromHeader,
                                        FromQuery,
                                        FromRoute,
                                        FromServices)

@app.router.put(b'/:d')
async def example(a: FromQuery(List[str]),
                  b: FromServices(Dog),
                  c: FromJson(Cat),
                  d: FromRoute(),
                  e: FromHeader(name='X-Example')):
    pass


@app.router.get(b'/:culture_code/:area')
async def home(request, culture_code, area):
    return text(f'Request for: {culture_code} {area}')
```
It also supports dependency injection, provided by [rodi](https://github.com/RobertoPrevato/rodi), a library from the same author, supporting `singleton`, `scoped`, and `transient` life style for activated services.

## Strategies to handle authentication and authorization
BlackSheep implements strategies to handle authentication and authorization, using [GuardPost](https://github.com/RobertoPrevato/GuardPost), a library from the same author.

```python
app.use_authentication()\
    .add(ExampleAuthenticationHandler())


app.use_authorization()\
    .add(AdminsPolicy())


@auth('admin')
@app.router.get(b'/')
async def only_for_admins():
    return None


@auth()
@app.router.get(b'/')
async def only_for_authenticated_users():
    return None
```

## Disclaimer
This project is currently targeting only __Linux__ and __CPython__: support for Windows and other implementations 
of Python language are currently out of the scope. However, support for PyPy and Windows is planned for the future. 

## Objectives
* Clean architecture and source code, following [SOLID principles](https://en.wikipedia.org/wiki/SOLID)
* Intelligible and easy to learn API, similar to those of many Python web frameworks
* Rich code API, based on Dependency Injection and inspired by ASP.NET Core
* Keep the core package minimal and focused, as much as possible, on features defined in HTTP and HTML standards
* Targeting stateless applications to be deployed in the cloud
* [High performance, see results from TechEmpower benchmarks (links in Wiki page)](https://github.com/RobertoPrevato/BlackSheep/wiki/Server-performance)

## Server Features
* [Routing](https://github.com/RobertoPrevato/BlackSheep/wiki/Routing)
* [Middlewares](https://github.com/RobertoPrevato/BlackSheep/wiki/Middlewares)
* [Built-in support for dependency injection](https://github.com/RobertoPrevato/BlackSheep/wiki/Dependency-injection)
* [Built-in support for multi processing](https://github.com/RobertoPrevato/BlackSheep/wiki/Built-in-multiprocessing)
* Integration with built-in `logging` module [to log access and errors](https://github.com/RobertoPrevato/BlackSheep/wiki/Logging) synchronously - this is completely disabled by default
* [Chunked encoding](https://github.com/RobertoPrevato/BlackSheep/wiki/Chunked-encoding) through generators (yield syntax)
* [Serving static files](https://github.com/RobertoPrevato/BlackSheep/wiki/Serving-static-files)
* [Integration with Jinja2](https://github.com/RobertoPrevato/BlackSheep/wiki/Jinja2)
* [Strategy to handle exceptions](https://github.com/RobertoPrevato/BlackSheep/wiki/Exceptions-handling)
* [Strategy to handle authentication and authorization](https://github.com/RobertoPrevato/BlackSheep/wiki/Authentication-and-authorization-strategies)
* [Handlers normalization](https://github.com/RobertoPrevato/BlackSheep/wiki/Handlers-normalization)
* [Support for automatic binding of route and query parameters to request handlers methods calls](https://github.com/RobertoPrevato/BlackSheep/wiki/Handlers-normalization#route-parameters)
* [Automatic reload of the application during development, adopted from Werkzeug framework and Flask](https://github.com/RobertoPrevato/BlackSheep/wiki/Automatic-reload)

## Client Features
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
        response = await client.get('https://docs.python.org/3/')

        assert response is not None
        text = await response.text()
        print(text)


loop = asyncio.get_event_loop()
loop.run_until_complete(client_example(loop))

```

## Note
This project is in beta stage. The reason behind this framework is described in this page of the Wiki: [Story](https://github.com/RobertoPrevato/BlackSheep/wiki/Story).

## Documentation
Please refer to the [project Wiki](https://github.com/RobertoPrevato/BlackSheep/wiki).

## Public project in Azure DevOps
[https://dev.azure.com/robertoprevato/BlackSheep](https://dev.azure.com/robertoprevato/BlackSheep) - see here the project in Azure DevOps, with [builds](https://dev.azure.com/robertoprevato/BlackSheep/_build?definitionId=7) and other goodness.
