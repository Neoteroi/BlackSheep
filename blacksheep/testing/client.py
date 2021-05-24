from urllib import parse

from blacksheep.messages import Request
from blacksheep.server.application import Application
from blacksheep.server.responses import Response
from blacksheep.testing.helpers import MockSend, get_example_scope


def _create_scope(method, path, headers: dict = None, query: dict = b"") -> dict:
    if headers is not None:
        headers = [(key.encode(), value.encode()) for key, value in headers.items()]

    if query:
        query = parse.urlencode(query).encode()

    scope = get_example_scope(method, path, extra_headers=headers, query=query)
    return scope


class _TestSimulator:
    def __init__(self, app, scope):
        self.app = app
        self.scope = scope
        self._prepare_application()

    async def simulate_request(self) -> Response:
        request = Request.incoming(
            self.scope["method"],
            self.scope["raw_path"],
            self.scope["query_string"],
            self.scope["headers"],
        )
        response = await self.app.handle(request)
        return response

    def _prepare_application(self):
        if self.app._service_provider is None:
            self.app.build_services()
            self.app.normalize_handlers()
            self.app.use_controllers()
            self.app.configure_middlewares()


async def _simulate_request(
    app: Application, method: str, path: str, headers: dict = None, query: dict = b""
):
    scope = _create_scope(method, path, headers, query)
    simulator = _TestSimulator(app, scope)
    return await simulator.simulate_request()


class TestClient:
    def __init__(self, app):
        self.app = app

    async def get(self, path: str, headers=None, query: dict = b""):
        return await _simulate_request(
            app=self.app, method="GET", path=path, headers=headers, query=query
        )

    async def post(self, path, headers=None, query: dict = b""):
        return await _simulate_request(
            app=self.app, method="POST", path=path, headers=headers, query=query
        )
