from blacksheep.server import ASGIApplication, Application
from blacksheep.server.responses import json

import uvicorn

application = Application()
app_three = ASGIApplication()


@application.router.get("/foo")
async def handle_foo(request):
    return json({"foo": "bar"})


@application.router.post("/post")
async def handle_post(request):
    data = await request.json()
    return json(data)


app_three.mount("/foo", app=application)
app_three.mount("/post", app=application)

if __name__ == "__main__":
    uvicorn.run(app_three, host="127.0.0.1", port=44557, log_level="debug")
