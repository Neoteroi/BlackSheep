import uvicorn
from blacksheep import text, Application, get


async def my_middleware(request, next_handler):
    raise ValueError


async def _exception_handler(app, request, exc: Exception):
    return text("Internal Server Error", 500)


app = Application()
app.exceptions_handlers[Exception] = _exception_handler

app.middlewares.append(my_middleware)


@get("/raise-error")
async def raise_error():
    1 / 0


uvicorn.run(app)
