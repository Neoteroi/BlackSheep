import uvicorn

from blacksheep.server import Application
from blacksheep.server.compression import use_gzip_compression
from blacksheep.server.responses import json

application = Application(show_error_details=True)
app_3 = Application(show_error_details=True)

use_gzip_compression(app_3)


@application.router.get("/foo")
def handle_foo():
    return json({"foo": "bar"})


@application.router.get("/admin/example.json")
def sub_folder_example():
    return json({"foo": "bar"})


@application.router.post("/")
async def handle_post(request):
    data = await request.json()
    return json(data)


async def on_start(_):
    await application.start()


async def on_stop(_):
    await application.stop()


app_3.on_start += on_start
app_3.on_stop += on_stop


app_3.mount("/foo", app=application)
app_3.mount("/post", app=application)

if __name__ == "__main__":
    uvicorn.run(app_3, host="127.0.0.1", port=44557, log_level="debug")
