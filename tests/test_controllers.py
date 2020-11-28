from functools import wraps
from typing import Optional

import pytest
from blacksheep import Request, Response
from blacksheep.server.application import RequiresServiceContainerError
from blacksheep.server.controllers import ApiController, Controller, RoutesRegistry
from blacksheep.server.responses import text
from blacksheep.server.routing import RouteDuplicate
from blacksheep.utils import ensure_str
from guardpost.authentication import User
from rodi import Services

from .test_application import FakeApplication, MockReceive, MockSend, get_example_scope


# NB: the following is an example of generic decorator (defined using *args and **kwargs)
# it is used to demonstrate that decorators can be used with normalized methods; however
# functools.@wraps is required,
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

    class Home(Controller):
        def greet(self):
            return "Hello World"

        @get("/")
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return text(self.greet())

        @get("/foo")
        async def foo(self):
            assert isinstance(self, Home)
            return text("foo")

    app.setup_controllers()
    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response.status == 200
    body = await app.response.text()
    assert body == "Hello World"

    await app(get_example_scope("GET", "/foo"), MockReceive(), MockSend())

    assert app.response.status == 200
    body = await app.response.text()
    assert body == "foo"


@pytest.mark.asyncio
async def test_handler_through_controller_owned_text_method():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):
        def greet(self):
            return "Hello World"

        @get("/")
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return self.text(self.greet())

        @get("/foo")
        async def foo(self):
            assert isinstance(self, Home)
            return self.text("foo")

    app.setup_controllers()
    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response.status == 200
    body = await app.response.text()
    assert body == "Hello World"

    await app(get_example_scope("GET", "/foo"), MockReceive(), MockSend())

    assert app.response.status == 200
    body = await app.response.text()
    assert body == "foo"


@pytest.mark.asyncio
async def test_controller_supports_on_request():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    k = 0

    class Home(Controller):
        def greet(self):
            return "Hello World"

        async def on_request(self, request: Request):
            nonlocal k
            k += 1
            assert isinstance(request, Request)
            assert request.url.path == b"/" if k < 10 else b"/foo"
            return await super().on_request(request)

        @get("/")
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return text(self.greet())

        @get("/foo")
        async def foo(self):
            assert isinstance(self, Home)
            return text("foo")

    app.setup_controllers()

    for j in range(1, 10):
        await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
        assert app.response.status == 200
        assert k == j

    for j in range(10, 20):
        await app(get_example_scope("GET", "/foo"), MockReceive(), MockSend())
        assert app.response.status == 200
        assert k == j


@pytest.mark.asyncio
async def test_controller_supports_on_response():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    k = 0

    class Home(Controller):
        def greet(self):
            return "Hello World"

        async def on_response(self, response: Response):
            nonlocal k
            k += 1
            assert isinstance(response, Response)
            if response.content.body == b"Hello World":
                assert k < 10
            else:
                assert k >= 10
            return await super().on_response(response)

        @get("/")
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return text(self.greet())

        @get("/foo")
        async def foo(self):
            assert isinstance(self, Home)
            return text("foo")

    app.setup_controllers()

    for j in range(1, 10):
        await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
        assert app.response.status == 200
        assert k == j

    for j in range(10, 20):
        await app(get_example_scope("GET", "/foo"), MockReceive(), MockSend())
        assert app.response.status == 200
        assert k == j


@pytest.mark.asyncio
async def test_handler_through_controller_supports_generic_decorator():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):
        def greet(self):
            return "Hello World"

        @get("/")
        @example()
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return text(self.greet())

    app.setup_controllers()
    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    body = await app.response.text()
    assert body == "Hello World"
    assert app.response.status == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["Hello World", "Charlie Brown"])
async def test_controller_with_dependency(value):
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Settings:
        def __init__(self, greetings: str):
            self.greetings = greetings

    class Home(Controller):
        def __init__(self, settings: Settings):
            assert isinstance(settings, Settings)
            self.settings = settings

        def greet(self):
            return self.settings.greetings

        @get("/")
        async def index(self, request: Request):
            return text(self.greet())

    app.services.add_instance(Settings(value))

    app.setup_controllers()
    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    body = await app.response.text()
    assert body == value
    assert app.response.status == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["Hello World", "Charlie Brown"])
async def test_many_controllers(value):
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Settings:
        def __init__(self, greetings: str):
            self.greetings = greetings

    class Home(Controller):
        def __init__(self, settings: Settings):
            self.settings = settings

        def greet(self):
            return self.settings.greetings

        @get("/")
        async def index(self, request: Request):
            return text(self.greet())

    class Foo(Controller):
        @get("/foo")
        async def foo(self, request: Request):
            return text("foo")

    app.services.add_instance(Settings(value))

    app.setup_controllers()
    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    body = await app.response.text()
    assert body == value
    assert app.response.status == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first_pattern,second_pattern",
    [
        ("/", "/"),
        (b"/", b"/"),
        (b"/", "/"),
        ("/", b"/"),
        ("/home", "/home/"),
        (b"/home", b"/home/"),
        ("/home", "/home//"),
        (b"/home", b"/home//"),
        ("/hello/world", "/hello/world/"),
        (b"/hello/world", b"/hello/world//"),
        ("/a/b", "/a/b"),
    ],
)
async def test_controllers_with_duplicate_routes_throw(first_pattern, second_pattern):
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class A(Controller):
        @get(first_pattern)
        async def index(self, request: Request):
            ...

    class B(Controller):
        @get(second_pattern)
        async def index(self, request: Request):
            ...

    with pytest.raises(RouteDuplicate) as context:
        app.use_controllers()

    error = context.value
    assert "Cannot register route pattern `" + ensure_str(
        first_pattern
    ) + "` for `GET` more than once." in str(error)
    assert (
        "This pattern is already registered for handler "
        "test_controllers_with_duplicate_routes_throw.<locals>.A.index." in str(error)
    )


@pytest.mark.asyncio
async def test_controller_on_request_setting_identity():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):
        async def on_request(self, request: Request):
            request.identity = User({"id": "001", "name": "Charlie Brown"}, "JWTBearer")

        @get("/")
        async def index(self, request: Request, user: Optional[User]):
            assert hasattr(request, "identity")
            assert isinstance(request.identity, User)
            return text(request.identity.name)

    app.setup_controllers()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    body = await app.response.text()
    assert body == "Charlie Brown"
    assert app.response.status == 200


@pytest.mark.asyncio
async def test_controller_with_base_route_as_string_attribute():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):

        route = "/home"

        def greet(self):
            return "Hello World"

        @get()
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return text(self.greet())

    app.setup_controllers()
    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response.status == 404

    await app(get_example_scope("GET", "/home"), MockReceive(), MockSend())
    assert app.response.status == 200
    body = await app.response.text()
    assert body == "Hello World"

    await app(get_example_scope("GET", "/home/"), MockReceive(), MockSend())
    assert app.response.status == 200
    body = await app.response.text()
    assert body == "Hello World"


@pytest.mark.asyncio
async def test_application_raises_for_invalid_route_class_attribute():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):

        route = False

        def greet(self):
            return "Hello World"

        @get()
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return text(self.greet())

    with pytest.raises(RuntimeError):
        app.setup_controllers()


@pytest.mark.asyncio
async def test_application_raises_for_controllers_for_invalid_services():
    app = FakeApplication(services=Services())
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):
        def greet(self):
            return "Hello World"

        @get()
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return text(self.greet())

    with pytest.raises(RequiresServiceContainerError):
        app.setup_controllers()


@pytest.mark.asyncio
async def test_controller_with_base_route_as_class_method():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Api(Controller):
        @classmethod
        def route(cls):
            return cls.__name__.lower()

    class Home(Api):
        def greet(self):
            return "Hello World"

        @get()
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return text(self.greet())

    class Health(Api):
        @get()
        def alive(self):
            return text("Good")

    app.setup_controllers()
    await app(get_example_scope("GET", "/home"), MockReceive(), MockSend())
    assert app.response.status == 200
    body = await app.response.text()
    assert body == "Hello World"

    for value in {"/Health", "/health"}:
        await app(get_example_scope("GET", value), MockReceive(), MockSend())
        assert app.response.status == 200
        body = await app.response.text()
        assert body == "Good"


@pytest.mark.asyncio
async def test_controller_with_base_route_as_class_method_fragments():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Api(Controller):
        @classmethod
        def route(cls):
            return "/api/" + cls.__name__.lower()

    class Home(Api):
        def greet(self):
            return "Hello World"

        @get()
        async def index(self, request: Request):
            assert isinstance(self, Home)
            return text(self.greet())

    class Health(Api):
        @get()
        def alive(self):
            return text("Good")

    app.setup_controllers()
    await app(get_example_scope("GET", "/api/home"), MockReceive(), MockSend())
    assert app.response.status == 200
    body = await app.response.text()
    assert body == "Hello World"

    for value in {"/api/Health", "/api/health"}:
        await app(get_example_scope("GET", value), MockReceive(), MockSend())
        assert app.response.status == 200
        body = await app.response.text()
        assert body == "Good"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first_pattern,second_pattern", [("/", "/home"), (b"/", b"/home")]
)
async def test_controllers_with_duplicate_routes_with_base_route_throw(
    first_pattern, second_pattern
):
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    # NB: this test creates ambiguity between the full route of a controller handler,
    # and another handler

    class A(Controller):

        route = "home"

        @get(first_pattern)
        async def index(self, request: Request):
            ...

    class B(Controller):
        @get(second_pattern)
        async def index(self, request: Request):
            ...

    with pytest.raises(RouteDuplicate):
        app.use_controllers()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first_pattern,second_pattern", [("/", "/home"), (b"/", b"/home")]
)
async def test_controller_with_duplicate_route_with_base_route_throw(
    first_pattern, second_pattern
):
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    # NB: this test creates ambiguity between the full route of a controller handler,
    # and another handler

    class A(Controller):

        route = "home"

        @get(first_pattern)
        async def index(self, request: Request):
            ...

    @app.route(second_pattern)
    async def home():
        ...

    with pytest.raises(RouteDuplicate):
        app.use_controllers()


@pytest.mark.asyncio
async def test_api_controller_without_version():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get
    post = app.controllers_router.post
    delete = app.controllers_router.delete
    patch = app.controllers_router.patch

    class Cat(ApiController):
        @get(":cat_id")
        def get_cat(self, cat_id: str):
            return text("1")

        @patch()
        def update_cat(self):
            return text("2")

        @post()
        def create_cat(self):
            return text("3")

        @delete(":cat_id")
        def delete_cat(self):
            return text("4")

    app.setup_controllers()

    expected_result = {
        ("GET", "/api/cat/100"): "1",
        ("PATCH", "/api/cat"): "2",
        ("POST", "/api/cat"): "3",
        ("DELETE", "/api/cat/100"): "4",
    }

    for key, value in expected_result.items():
        method, pattern = key
        await app(get_example_scope(method, pattern), MockReceive(), MockSend())

        assert app.response.status == 200
        body = await app.response.text()
        assert body == value


@pytest.mark.asyncio
async def test_api_controller_with_version():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get
    post = app.controllers_router.post
    delete = app.controllers_router.delete
    patch = app.controllers_router.patch

    class Cat(ApiController):
        @classmethod
        def version(cls) -> Optional[str]:
            return "v1"

        @get(":cat_id")
        def get_cat(self, cat_id: str):
            return text("1")

        @patch()
        def update_cat(self):
            return text("2")

        @post()
        def create_cat(self):
            return text("3")

        @delete(":cat_id")
        def delete_cat(self):
            return text("4")

    app.setup_controllers()

    expected_result = {
        ("GET", "/api/v1/cat/100"): "1",
        ("PATCH", "/api/v1/cat"): "2",
        ("POST", "/api/v1/cat"): "3",
        ("DELETE", "/api/v1/cat/100"): "4",
    }

    for key, value in expected_result.items():
        method, pattern = key
        await app(get_example_scope(method, pattern), MockReceive(), MockSend())

        assert app.response.status == 200
        body = await app.response.text()
        assert body == value


@pytest.mark.asyncio
async def test_api_controller_with_version_2():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get
    post = app.controllers_router.post
    delete = app.controllers_router.delete
    patch = app.controllers_router.patch

    class CatV1(ApiController):
        @classmethod
        def version(cls) -> Optional[str]:
            return "v1"

        @get(":cat_id")
        def get_cat(self, cat_id: str):
            return text("1")

        @patch()
        def update_cat(self):
            return text("2")

        @post()
        def create_cat(self):
            return text("3")

        @delete(":cat_id")
        def delete_cat(self):
            return text("4")

    class CatV2(ApiController):
        @classmethod
        def version(cls) -> Optional[str]:
            return "v2"

        @get(":cat_id")
        def get_cat(self, cat_id: str):
            return text("5")

        @patch()
        def update_cat(self):
            return text("6")

        @post()
        def create_cat(self):
            return text("7")

        @delete(":cat_id")
        def delete_cat(self):
            return text("8")

    app.setup_controllers()

    expected_result = {
        ("GET", "/api/v1/cat/100"): "1",
        ("PATCH", "/api/v1/cat"): "2",
        ("POST", "/api/v1/cat"): "3",
        ("DELETE", "/api/v1/cat/100"): "4",
        ("GET", "/api/v2/cat/100"): "5",
        ("PATCH", "/api/v2/cat"): "6",
        ("POST", "/api/v2/cat"): "7",
        ("DELETE", "/api/v2/cat/100"): "8",
    }

    for key, value in expected_result.items():
        method, pattern = key
        await app(get_example_scope(method, pattern), MockReceive(), MockSend())

        assert app.response.status == 200
        body = await app.response.text()
        assert body == value


@pytest.mark.asyncio
async def test_controller_parameter_name_match():
    app = FakeApplication()
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Example(Controller):
        @get("/")
        async def from_query(self, example: str):
            assert isinstance(self, Example)
            assert isinstance(example, str)
            return text(example)

        @get("/{example}")
        async def from_route(self, example: str):
            assert isinstance(self, Example)
            assert isinstance(example, str)
            return text(example)

    app.setup_controllers()
    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response.status == 400
    body = await app.response.text()
    assert body == "Bad Request: Missing query parameter `example`"

    await app(get_example_scope("GET", "/foo"), MockReceive(), MockSend())

    assert app.response.status == 200
    body = await app.response.text()
    assert body == "foo"
