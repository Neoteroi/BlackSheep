"""
Benchmarks testing end-2-end handling of HTTP requests, mocking ASGI scopes.
"""

from functools import partial
from pathlib import Path

from blacksheep import Application, Response, Router
from blacksheep.contents import TextContent
from blacksheep.server.controllers import Controller
from blacksheep.server.responses import text
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from perf.benchmarks import async_benchmark, main_run

ITERATIONS = 10000
LOREM_IPSUM = (Path(__file__).parent / "res" / "lorem.txt").read_text(encoding="utf-8")
REQUEST_HEADERS = [
    (b"Connection", b"keep-alive"),
    (b"Cache-Control", b"max-age=0"),
    (
        b"sec-ch-ua",
        b'"Chromium";v="112", "Google Chrome";v="112", "Not:A-Brand";v="99"',
    ),
    (b"sec-ch-ua-mobile", b"?0"),
    (b"sec-ch-ua-platform", b'"Windows"'),
    (b"Upgrade-Insecure-Requests", b"1"),
    (
        b"User-Agent",
        b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
    ),
    (
        b"Accept",
        b"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    ),
    (b"Sec-Fetch-Site", b"none"),
    (b"Sec-Fetch-Mode", b"navigate"),
    (b"Sec-Fetch-User", b"?1"),
    (b"Sec-Fetch-Dest", b"document"),
    (b"Accept-Encoding", b"gzip, deflate, br"),
    (b"Accept-Language", b"en-US,en;q=0.9"),
]
RESPONSE_HEADERS = [
    (b"Content-Type", b"text/html; charset=utf-8"),
    (b"Content-Length", b"123"),
    (b"Connection", b"keep-alive"),
    (b"Cache-Control", b"no-cache, no-store, must-revalidate"),
    (b"Pragma", b"no-cache"),
    (b"Expires", b"0"),
    (b"X-Frame-Options", b"DENY"),
    (b"X-Content-Type-Options", b"nosniff"),
    (b"X-XSS-Protection", b"1; mode=block"),
    (b"Strict-Transport-Security", b"max-age=31536000; includeSubDomains"),
    (b"Server", b"BlackSheep/1.0"),
]


async def test_app_handle_small_response(application: Application):
    scope = get_example_scope(
        "GET", "/test", extra_headers=REQUEST_HEADERS, query=b"q=1&x=2"
    )
    mock_send = MockSend()
    await application(scope, MockReceive(), mock_send)
    assert mock_send.messages[1]["body"] == b"Hello, World!"


async def test_app_handle_small_response_with_qs(application: Application):
    scope = get_example_scope(
        "GET", "/test", extra_headers=REQUEST_HEADERS, query=b"name=World"
    )
    mock_send = MockSend()
    await application(scope, MockReceive(), mock_send)
    assert mock_send.messages[1]["body"] == b"Hello, World"


async def test_app_handle_text_response(application: Application):
    scope = get_example_scope("GET", "/test", extra_headers=REQUEST_HEADERS)
    mock_send = MockSend()
    await application(scope, MockReceive(), mock_send)
    assert len(mock_send.messages) == 2


async def benchmark_app_handle_small_response(iterations=ITERATIONS):
    application = Application(router=Router())
    application.router.add_get("/test", lambda _: "Hello, World!")
    await application.start()
    return await async_benchmark(
        partial(test_app_handle_small_response, application), iterations
    )


async def benchmark_app_handle_small_response_with_qs(iterations=ITERATIONS):
    application = Application(router=Router())

    @application.router.get("/test")
    def handle(name: str) -> Response:
        return text(f"Hello, {name}")

    await application.start()
    return await async_benchmark(
        partial(test_app_handle_small_response_with_qs, application), iterations
    )


async def benchmark_app_handle_text_response(iterations=ITERATIONS):
    application = Application(router=Router())

    @application.router.get("/test")
    async def test_handler() -> Response:
        return Response(200, RESPONSE_HEADERS).with_content(TextContent(LOREM_IPSUM))

    await application.start()
    return await async_benchmark(
        partial(test_app_handle_text_response, application), iterations
    )


async def benchmark_app_handle_small_response_controller(iterations=ITERATIONS):
    application = Application(router=Router())

    class TestController(Controller):
        @application.router.controllers_routes.get("/test")
        def hello_world(self) -> Response:
            return self.text("Hello, World!")

    await application.start()
    return await async_benchmark(
        partial(test_app_handle_small_response, application), iterations
    )


async def benchmark_app_handle_small_response_controller_with_qs(iterations=ITERATIONS):
    application = Application(router=Router())

    class TestController(Controller):
        @application.router.controllers_routes.get("/test")
        def hello_world(self, name: str) -> Response:
            return self.text(f"Hello, {name}")

    await application.start()
    return await async_benchmark(
        partial(test_app_handle_small_response_with_qs, application), iterations
    )


async def benchmark_app_handle_text_response_controller(iterations=ITERATIONS):
    application = Application(router=Router())

    class TestController(Controller):
        @application.router.controllers_routes.get("/test")
        def hello_world(self) -> Response:
            return self.text(LOREM_IPSUM)

    await application.start()
    return await async_benchmark(
        partial(test_app_handle_text_response, application), iterations
    )


if __name__ == "__main__":
    main_run(benchmark_app_handle_small_response_with_qs)
