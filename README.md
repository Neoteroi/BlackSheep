# BlackSheep
HTTP Server/Client microframework for Python asyncio, using [Cython](https://cython.org), 
[`uvloop`](https://magic.io/blog/uvloop-blazing-fast-python-networking/), and 
[`httptools`](https://github.com/MagicStack/httptools). 

This project is a beta version.

```python
from datetime import datetime
from blacksheep.server import Application
from blacksheep.entities import HttpResponse, TextContent


app = Application()

@app.route('/')
async def home(request):
    return HttpResponse(200, content=TextContent(f'Hello, World! {datetime.utcnow().isoformat()}'))

app.start()
```

## Objectives
* Clean architecture and clean source code
* Avoid CPU cycles to handle things that are not strictly necessary
* Intelligible and easy to learn API, similar to those of many Python web frameworks
* Keep the core package minimal and focused, as much as possible, on features defined in HTTP and HTML standards
* High performance

## Server Features
* Routing
* Middlewares
* Built-in support for multi processing
* Integration with built-in `logging` module to log access and errors synchronously - this is completely disabled by default
* Chunked encoding through generators (yield syntax)
* Serving static files
* __Linux only__: support for Windows is currently out of the scope of this project

## Documentation
Please refer to the [project Wiki](https://github.com/RobertoPrevato/BlackSheep/wiki).
