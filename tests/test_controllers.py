import pytest
from typing import Optional
from functools import wraps
from blacksheep import Request
from blacksheep.server.responses import text
from blacksheep.server.controllers import Controller, RoutesRegistry
from blacksheep.server.routing import RouteDuplicate
from guardpost.authentication import User
from .test_application import FakeApplication, MockReceive, MockSend, get_example_scope


# NB: the following is an example of generic decorator (defined using *args and **kwargs)
# it is used to demonstrate that decorators can be used with normalized methods; however functools.@wraps is required,
# so it is the order (custom decorators must appear after router decorators)
def example():
    def example_decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            return await fn(*args, **kwargs)
        return wrapper
    return example_decorator


@pytest.mark.asyncio
async def test_handler_through_controller():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    # noinspection PyUnusedLocal
    class Home(Controller):

        def greet(self):
            return 'Hello World'

        @get('/')
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return text(self.greet())

        @get('/foo')
        async def foo(self):
            assert isinstance(self, Home)
            return text('foo')

    app.setup_controllers()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())

    assert app.response.status == 200
    body = await app.response.text()
    assert body == 'Hello World'

    await app(get_example_scope('GET', '/foo'), MockReceive(), MockSend())

    assert app.response.status == 200
    body = await app.response.text()
    assert body == 'foo'


@pytest.mark.asyncio
async def test_controller_supports_on_request():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    k = 0

    # noinspection PyUnusedLocal
    class Home(Controller):

        def greet(self):
            return 'Hello World'

        async def on_request(self, request: Request):
            nonlocal k
            k += 1
            assert isinstance(request, Request)
            assert request.url.path == b'/' if k < 10 else b'/foo'
            return await super().on_request(request)

        @get('/')
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return text(self.greet())

        @get('/foo')
        async def foo(self):
            assert isinstance(self, Home)
            return text('foo')

    app.setup_controllers()

    for j in range(1, 10):
        await app(get_example_scope('GET', '/'), MockReceive(), MockSend())
        assert app.response.status == 200
        assert k == j

    for j in range(10, 20):
        await app(get_example_scope('GET', '/foo'), MockReceive(), MockSend())
        assert app.response.status == 200
        assert k == j


@pytest.mark.asyncio
async def test_handler_through_controller_supports_generic_decorator():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    # noinspection PyUnusedLocal
    class Home(Controller):

        def greet(self):
            return 'Hello World'

        @get('/')
        @example()
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return text(self.greet())

    app.setup_controllers()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())

    body = await app.response.text()
    assert body == 'Hello World'
    assert app.response.status == 200


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [
    'Hello World', 'Charlie Brown'
])
async def test_controller_with_dependency(value):
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Settings:

        def __init__(self, greetings: str):
            self.greetings = greetings

    # noinspection PyUnusedLocal
    class Home(Controller):

        def __init__(self, settings: Settings):
            assert isinstance(settings, Settings)
            self.settings = settings

        def greet(self):
            return self.settings.greetings

        @get('/')
        async def index(self, request: Request):
            return text(self.greet())

    app.services.add_instance(Settings(value))

    app.setup_controllers()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())

    body = await app.response.text()
    assert body == value
    assert app.response.status == 200


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [
    'Hello World', 'Charlie Brown'
])
async def test_many_controllers(value):
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
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

    app.setup_controllers()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())

    body = await app.response.text()
    assert body == value
    assert app.response.status == 200


@pytest.mark.asyncio
async def test_controllers_with_duplicate_routes_throw():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    # noinspection PyUnusedLocal
    class A(Controller):

        @get('/')
        async def index(self, request: Request): ...

    # noinspection PyUnusedLocal
    class B(Controller):

        @get('/')
        async def index(self, request: Request): ...

    with pytest.raises(RouteDuplicate):
        app.use_controllers()


@pytest.mark.asyncio
async def test_controller_on_request_setting_identity():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    # noinspection PyUnusedLocal
    class Home(Controller):

        async def on_request(self, request: Request):
            request.identity = User({'id': '001', 'name': 'Charlie Brown'}, 'JWTBearer')

        @get('/')
        async def index(self, request: Request, user: Optional[User]):
            assert hasattr(request, 'identity')
            assert isinstance(request.identity, User)
            return text(request.identity.name)

    app.setup_controllers()

    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())
    body = await app.response.text()
    assert body == 'Charlie Brown'
    assert app.response.status == 200


@pytest.mark.asyncio
async def test_controller_with_base_route():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    # noinspection PyUnusedLocal
    class Home(Controller):
        
        route = '/home'

        def greet(self):
            return 'Hello World'

        @get('/')
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return text(self.greet())

    app.setup_controllers()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())
    assert app.response.status == 404

    await app(get_example_scope('GET', '/home'), MockReceive(), MockSend())
    assert app.response.status == 200
    body = await app.response.text()
    assert body == 'Hello World'

    await app(get_example_scope('GET', '/home/'), MockReceive(), MockSend())
    assert app.response.status == 200
    body = await app.response.text()
    assert body == 'Hello World'
