# BlackSheep
HTTP Server/Client microframework for Python asyncio, using [Cython](https://cython.org), 
[`uvloop`](https://magic.io/blog/uvloop-blazing-fast-python-networking/), and 
[`httptools`](https://github.com/MagicStack/httptools). 

This project is a beta version. The reason behind this framework is described in this page of the Wiki: [Story](https://github.com/RobertoPrevato/BlackSheep/wiki/Story).

```python
from datetime import datetime
from blacksheep import HttpResponse, TextContent
from blacksheep.server import Application


app = Application()

@app.route('/')
async def home(request):
    return HttpResponse(200, content=TextContent(f'Hello, World! {datetime.utcnow().isoformat()}'))

app.start()
```

## Objectives
* Clean architecture and source code
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

## Documentation
Please refer to the [project Wiki](https://github.com/RobertoPrevato/BlackSheep/wiki).
