from blacksheep import Application
from blacksheep.server.controllers import Controller, get


app = Application()


class BaseController(Controller):
    @get("/hello-world")
    def index(self):
        # This route must only be set by final subclasses, since this class has
        # controllers subclasses.
        print(self)
        return self.text("Hello, World!")


class ControllerOne(BaseController):
    route = "/one"

    # /one/hello-world


class ControllerTwo(BaseController):
    route = "/two"

    # /two/hello-world

    @get("/specific-route")  # /two/specific-route
    def specific_route(self):
        print(self)
        assert isinstance(self, ControllerTwo)
        return self.text("This is a specific route in ControllerTwo")


class ControllerTwoBis(ControllerTwo):
    route = "/two-bis"

    # /two-bis/hello-world

    # /two-bis/specific-route

    @get("/specific-route-2")  # /two-bis/specific-route-2
    def specific_route(self):
        print(self)
        assert isinstance(self, ControllerTwoBis)
        return self.text("This is a specific route in ControllerTwoBis")


@app.after_start
async def after_start():
    if len(app.router.routes[b"GET"]) < 7:
        print("Routes not registered correctly")
    print(app.router.routes)


"""
Quando valuto ogni route:
1. Devo registrare una route simile per ogni sottoclasse!
"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, port=44777)
