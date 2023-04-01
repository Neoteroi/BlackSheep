from functools import partial
from pprint import pprint
from typing import ClassVar, List

from rodi import Container

from blacksheep import Application
from blacksheep.server.controllers import Controller, filters, get
from blacksheep.server.routing import Router, HeadersFilter

area_51 = Router(headers={"X-Area": "51"})
main_router = Router(sub_routers=[area_51])
app = Application(router=main_router)


assert isinstance(app.services, Container)

special = partial(filters, headers={"X-Area": "Special"})


special = partial(filters, host="neoteroi.dev", headers={"X-Area": "Special"})


@special()
class Special(Controller):
    _filters_ = (HeadersFilter({"X-Area": "Special"}),)

    @get("/")
    def special(self):
        return self.text("Special")


@special()
class Special2(Controller):
    @get("/special2")
    def special(self):
        return self.text("Special")


@app.after_start
async def log_routes():
    pprint(list(app.router))


@main_router.get("/")
def home():
    return "Home"


@area_51.get("/")
def secret_home():
    return "Boo"


@main_router.get("/another")
def another():
    return "Another"


@main_router.get("/{param}")
def echo(param):
    return param


@area_51.get("/another")
def secret_another():
    return "Another Secret"


@area_51.get("/{param}")
def echo2(param):
    return param + " 51"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=44777, log_level="debug", lifespan="on")
