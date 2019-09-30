import pytest
from .test_application import FakeApplication, MockReceive, MockSend, get_example_scope
from blacksheep import Request
from blacksheep.server.responses import text
from blacksheep.server.controllers import Controller, Router


@pytest.mark.asyncio
async def test_handler_through_controller():
    app = FakeApplication()
    app.controllers_router = Router()
    get = app.controllers_router.get

    # noinspection PyUnusedLocal
    class Home(Controller):

        def greet(self):
            return 'Hello World'

        @get('/')
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return text(self.greet())

    app.use_controllers()
    app.build_services()
    app.normalize_handlers()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())

    assert app.response.status == 200
    body = await app.response.text()
    assert body == 'Hello World'


@pytest.mark.asyncio
async def test_controller_with_dependency():
    app = FakeApplication()
    app.controllers_router = Router()
    get = app.controllers_router.get

    value = 'Hello World'

    class Settings:

        def __init__(self, greetings: str):
            self.greetings = greetings

    # noinspection PyUnusedLocal
    class Home(Controller):

        def __init__(self, settings: Settings):
            self.settings = settings

        def greet(self):
            return self.settings.greetings

        @get('/')
        async def index(self, request: Request):
            return text(self.greet())

    app.services.add_instance(Settings(value))

    app.use_controllers()
    app.build_services()
    app.normalize_handlers()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())
    assert app.response.status == 200

    body = await app.response.text()
    assert body == value


@pytest.mark.asyncio
async def test_many_controllers():
    value = 'Hello World'

    app = FakeApplication()
    app.controllers_router = Router()
    get = app.controllers_router.get

    class Settings:

        def __init__(self, greetings: str):
            self.greetings = greetings

    # noinspection PyUnusedLocal
    class Home(Controller):

        def __init__(self, settings: Settings):
            self.settings = settings

        def greet(self):
            return self.settings.greetings

        @get('/')
        async def index(self, request: Request):
            return text(self.greet())

    # noinspection PyUnusedLocal
    class Foo(Controller):

        @get('/foo')
        async def foo(self, request: Request):
            return text('foo')

    app.services.add_instance(Settings(value))

    app.use_controllers()
    app.build_services()
    app.normalize_handlers()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())
    assert app.response.status == 200

    body = await app.response.text()
    assert body == value

