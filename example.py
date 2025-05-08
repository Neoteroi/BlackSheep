from blacksheep import Application
from blacksheep.server.controllers import Controller, abstract, get

app = Application()


@abstract()
class BaseController(Controller):
    @get("/hello-world")
    def index(self):
        # Note: the route /hello-world itself will not be registered in the router,
        # because this class is decorated with @abstract()
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
    if len(app.router.routes[b"GET"]) != 6:
        print("Routes not registered correctly")
    print(app.router.routes)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, port=44777)
