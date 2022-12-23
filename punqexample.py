from typing import Type, TypeVar, Union, cast

import punq

from blacksheep import Application
from blacksheep.messages import Request
from blacksheep.server.controllers import Controller, get

T = TypeVar("T")


class Foo:
    def __init__(self) -> None:
        self.foo = "Foo"


class PunqDI:
    def __init__(self, container: punq.Container) -> None:
        self.container = container

    def register(self, obj_type, *args):
        self.container.register(obj_type, *args)

    def resolve(self, obj_type: Union[Type[T], str], *args) -> T:
        return cast(T, self.container.resolve(obj_type))

    def __contains__(self, item) -> bool:
        return bool(self.container.registrations[item])


container = punq.Container()
container.register(Foo)

x = Foo in PunqDI(container)

app = Application(services=PunqDI(container), show_error_details=True)


@app.route("/")
def home(foo: Foo):  # <-- foo is referenced in type annotation
    return f"Hello, {foo.foo}!"


class Settings:
    def __init__(self, greetings: str):
        self.greetings = greetings


container.register(Settings, instance=Settings("example"))


class Home(Controller):
    def __init__(self, settings: Settings):
        # controllers are instantiated dynamically at every web request
        self.settings = settings

    async def on_request(self, request: Request):
        print("[*] Received a request!!")

    def greet(self):
        return self.settings.greetings

    @get("/home")
    async def index(self):
        return self.greet()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=44777, log_level="debug")
