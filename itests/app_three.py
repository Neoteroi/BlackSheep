import uvicorn

from blacksheep.server import Application
from blacksheep.server.responses import json

application = Application(show_error_details=True)
app_three = Application(show_error_details=True)


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


app_three.on_start += on_start
app_three.on_stop += on_stop


app_three.mount("/foo", app=application)
app_three.mount("/post", app=application)

if __name__ == "__main__":
    uvicorn.run(app_three, host="127.0.0.1", port=44557, log_level="debug")
