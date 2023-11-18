from dataclasses import dataclass
from functools import wraps
from typing import Optional

import pytest
from guardpost import AuthenticationHandler, User
from rodi import inject

from blacksheep import Request, Response
from blacksheep.server.application import Application
from blacksheep.server.controllers import (
    APIController,
    Controller,
    RoutesRegistry,
    filters,
)
from blacksheep.server.di import register_http_context
from blacksheep.server.responses import text
from blacksheep.server.routing import RouteDuplicate
from blacksheep.server.websocket import WebSocket
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from blacksheep.utils import ensure_str
from tests.test_files_serving import get_file_path


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
async def test_handler_through_controller(app):
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
async def test_ws_handler_through_controller(app):
    app.controllers_router = RoutesRegistry()
    ws = app.controllers_router.ws

    called = False

    class Home(Controller):
        @ws("/web-socket")
        async def foo(self, websocket):
            nonlocal called
            called = True
            assert isinstance(self, Home)
            assert isinstance(websocket, WebSocket)
            await websocket.accept()

    app.setup_controllers()
    await app(
        {"type": "websocket", "path": "/web-socket", "query_string": "", "headers": []},
        MockReceive([{"type": "websocket.connect"}]),
        MockSend(),
    )

    assert called is True


@pytest.mark.asyncio
async def test_user_binder_with_controller(app):
    """
    The following test covers the scenario where the User object is first
    bound to a request handler using the dedicated Binder (this allows to keep separated
    runtime values like HTTP context and user from DI composition data like classes that
    do not depend on a runtime scope), and using dependency injection (this requires
    mixing runtime values and composition data).

    In the Home controller below, the User is passed to the request handler using a
    Binder; in the Another controller the User is instead injected using DI.
    The second scenario requires registering the HTTP Context and User factory to obtain
    the scoped services. The second scenario has the benefit that the User context can
    be injected at any point of the activation chain (e.g. in the business logic layer),
    but it has the negative side to mix runtime values with composition data.
    """
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class MockAuthHandler(AuthenticationHandler):
        async def authenticate(self, context):
            context.user = User({"name": "Dummy"}, "TEST")
            return context.user

    app.use_authentication().add(MockAuthHandler())
    called = False

    class Home(Controller):
        @get("/1")
        async def home(self, user: User):
            nonlocal called
            called = True
            assert isinstance(self, Home)
            assert isinstance(user, User)
            assert user.name == "Dummy"

    class Another(Controller):
        user: User

        @get("/2")
        async def home2(self):
            nonlocal called
            called = True
            assert isinstance(self, Another)
            assert isinstance(self.user, User)
            assert self.user.name == "Dummy"

    register_http_context(app)

    def user_factory(context) -> User:
        # The following scoped service is set in a middleware, since in fact we are
        # mixing runtime data with composition data.
        request = context.scoped_services[Request]
        return request.user or User()

    app.services.add_scoped_by_factory(user_factory)

    await app.start()
    await app(get_example_scope("GET", "/1"), MockReceive(), MockSend())
    assert called is True
    called = False
    await app(get_example_scope("GET", "/2"), MockReceive(), MockSend())
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path_one,path_two",
    [
        ["/<path:filepath>", "/example/<path:filepath>"],
        ["/{path:filepath}", "/example/{path:filepath}"],
    ],
)
async def test_handler_catch_all_through_controller(path_one, path_two, app):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):
        def greet(self):
            return "Hello World"

        @get(path_one)
        async def catch_all(self, filepath: str):
            assert isinstance(self, Home)
            assert isinstance(filepath, str)
            return text(filepath)

        @get(path_two)
        async def catch_all_under_example(self, filepath: str):
            assert isinstance(self, Home)
            assert isinstance(filepath, str)
            return text(f"Example: {filepath}")

        @get("/foo")
        async def foo(self):
            assert isinstance(self, Home)
            return text("foo")

    app.setup_controllers()
    await app(get_example_scope("GET", "/hello.js"), MockReceive(), MockSend())

    assert app.response.status == 200
    body = await app.response.text()
    assert body == "hello.js"

    await app(
        get_example_scope("GET", "/scripts/a/b/c/hello.js"), MockReceive(), MockSend()
    )

    assert app.response.status == 200
    body = await app.response.text()
    assert body == "scripts/a/b/c/hello.js"

    await app(
        get_example_scope("GET", "/example/a/b/c/hello.js"), MockReceive(), MockSend()
    )

    assert app.response.status == 200
    body = await app.response.text()
    assert body == "Example: a/b/c/hello.js"

    await app(get_example_scope("GET", "/foo"), MockReceive(), MockSend())

    assert app.response.status == 200
    body = await app.response.text()
    assert body == "foo"


@pytest.mark.asyncio
async def test_handler_through_controller_owned_text_method(app):
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
async def test_handler_through_controller_owned_html_method(app):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):
        @get("/")
        async def index(self):
            assert isinstance(self, Home)
            return self.html(
                """
                <h1>Title</h1>
                <p>Lorem ipsum</p>
                """
            )

    app.setup_controllers()
    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response.status == 200
    body = await app.response.text()
    assert "<h1>Title</h1>" in body
    assert "<p>Lorem ipsum</p>" in body
    assert app.response.content_type() == b"text/html; charset=utf-8"


@pytest.mark.asyncio
async def test_controller_supports_on_request(app):
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
async def test_controller_supports_on_response(app):
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
async def test_handler_through_controller_supports_generic_decorator(app):
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
async def test_controller_with_dependency(value, app: Application):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Settings:
        def __init__(self, greetings: str):
            self.greetings = greetings

    @inject()
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
async def test_many_controllers(value, app):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Settings:
        def __init__(self, greetings: str):
            self.greetings = greetings

    @inject()
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
async def test_controllers_with_duplicate_routes_throw(
    first_pattern, second_pattern, app
):
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
async def test_controller_on_request_setting_identity(app):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):
        async def on_request(self, request: Request):
            request.user = User({"id": "001", "name": "Charlie Brown"}, "JWTBearer")

        @get("/")
        async def index(self, request: Request, user: Optional[User]):
            assert hasattr(request, "identity")
            assert isinstance(request.user, User)
            return text(request.user["name"])

    app.setup_controllers()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    body = await app.response.text()
    assert body == "Charlie Brown"
    assert app.response.status == 200


@pytest.mark.asyncio
async def test_controller_with_base_route_as_string_attribute(app):
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
async def test_application_raises_for_invalid_route_class_attribute(app):
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
async def test_controller_with_base_route_as_class_method(app):
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
async def test_controller_with_base_route_as_class_method_fragments(app):
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
    first_pattern, second_pattern, app
):
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
    first_pattern, second_pattern, app
):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    # NB: this test creates ambiguity between the full route of a controller handler,
    # and another handler

    class A(Controller):
        route = "home"

        @get(first_pattern)
        async def index(self, request: Request):
            ...

    @app.router.route(second_pattern)
    async def home():
        ...

    with pytest.raises(RouteDuplicate):
        app.use_controllers()


@pytest.mark.asyncio
async def test_api_controller_without_version(app):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get
    post = app.controllers_router.post
    delete = app.controllers_router.delete
    patch = app.controllers_router.patch

    class Cat(APIController):
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
async def test_api_controller_with_version(app):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get
    post = app.controllers_router.post
    delete = app.controllers_router.delete
    patch = app.controllers_router.patch

    class Cat(APIController):
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
async def test_api_controller_with_version_2(app):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get
    post = app.controllers_router.post
    delete = app.controllers_router.delete
    patch = app.controllers_router.patch

    class CatV1(APIController):
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

    class CatV2(APIController):
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
async def test_controller_parameter_name_match(app):
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


@pytest.mark.asyncio
async def test_controller_return_file(app):
    file_path = get_file_path("example.config", "files2")

    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Example(Controller):
        @get("/")
        async def home(self):
            return self.file(file_path, "text/plain; charset=utf-8")

    app.setup_controllers()

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.headers.get_single(b"content-type") == b"text/plain; charset=utf-8"
    assert response.headers.get_single(b"content-disposition") == b"attachment"

    text = await response.text()
    with open(file_path, mode="rt", encoding="utf8") as f:
        contents = f.read()
        assert contents == text


@dataclass
class Foo:
    name: str
    value: float


@pytest.mark.asyncio
async def test_handler_through_controller_default_type(app):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):
        @get("/")
        async def index(self) -> Foo:
            return Foo("Hello", 5.5)

    app.setup_controllers()
    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response.status == 200
    data = await app.response.json()
    assert data == {"name": "Hello", "value": 5.5}


@pytest.mark.asyncio
async def test_handler_through_controller_default_str(app):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):
        @get("/")
        async def index(self) -> str:
            return "Hello World"

    app.setup_controllers()
    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response.status == 200
    data = await app.response.text()
    assert data == "Hello World"


@pytest.mark.asyncio
async def test_controller_filters(app):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    @filters(headers={"X-Area": "51"})
    class Home(Controller):
        @get("/")
        async def index(self) -> str:
            return "Hello World"

    app.setup_controllers()
    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response.status == 404

    await app(
        get_example_scope("GET", "/", extra_headers={"X-Area": "51"}),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    data = await app.response.text()
    assert data == "Hello World"
