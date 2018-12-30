# BlackSheep
HTTP Server/Client microframework for Python asyncio, using [Cython](https://cython.org), 
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
from blacksheep import Response, TextContent
from blacksheep.server import Application


app = Application()

@app.route('/')
async def home(request):
    return Response(200, content=TextContent(f'Hello, World! {datetime.utcnow().isoformat()}'))

app.start()
```

## Objectives
* Clean architecture and source code, following SOLID principles
* Avoid CPU cycles to handle things that are not strictly necessary
* Intelligible and easy to learn API, similar to those of many Python web frameworks
* Keep the core package minimal and focused, as much as possible, on features defined in HTTP and HTML standards
* High performance

## Server Features
* [Routing](https://github.com/RobertoPrevato/BlackSheep/wiki/Routing)
* [Middlewares](https://github.com/RobertoPrevato/BlackSheep/wiki/Middlewares)
* [Built-in support for multi processing](https://github.com/RobertoPrevato/BlackSheep/wiki/Built-in-multiprocessing)
* Integration with built-in `logging` module [to log access and errors](https://github.com/RobertoPrevato/BlackSheep/wiki/Logging) synchronously - this is completely disabled by default
* [Chunked encoding](https://github.com/RobertoPrevato/BlackSheep/wiki/Chunked-encoding) through generators (yield syntax)
* [Serving static files](https://github.com/RobertoPrevato/BlackSheep/wiki/Serving-static-files)
* __Linux only__: support for Windows is currently out of the scope of this project

## Client Features
* Support for client side middlewares, enabling clean source code and separation of concerns (logging of different kinds, handling of cookies, etc.)
* HTTP connection pooling
* User friendly handling of SSL contexts (safe by default)
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
This project is in alpha stage. The reason behind this framework is described in this page of the Wiki: [Story](https://github.com/RobertoPrevato/BlackSheep/wiki/Story).

## Documentation
Please refer to the [project Wiki](https://github.com/RobertoPrevato/BlackSheep/wiki).
