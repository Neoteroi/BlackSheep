import abc
import json
from typing import Any, Dict, Optional
from urllib import parse

from blacksheep.contents import ASGIContent
from blacksheep.messages import Request
from blacksheep.server.responses import Response
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive


def _create_scope(
    method: str,
    path: str,
    headers: Optional[Dict[str, str]] = None,
    query: Optional[Dict[str, str]] = b"",
) -> Dict:
    if headers is not None:
        headers = [(key.encode(), value.encode()) for key, value in headers.items()]

    if query:
        query = parse.urlencode(query).encode()

    scope = get_example_scope(method, path, extra_headers=headers, query=query)
    return scope


class AbstractTestSimulator:
    @abc.abstractmethod
    async def send_request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query: Optional[Dict[str, str]] = b"",
        content: Dict[str, Any] = None,
    ):
        pass


class TestSimulator(AbstractTestSimulator):
    def __init__(self, app):
        self.app = app
        self._prepare_application()

    async def send_request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query: Optional[Dict[str, str]] = b"",
        content: Optional[Dict[str, Any]] = None,
    ) -> Response:

        scope = _create_scope(method, path, headers, query)
        request = Request.incoming(
            scope["method"],
            scope["raw_path"],
            scope["query_string"],
            scope["headers"],
        )

        request.scope = scope

        if content is not None:
            encoded_content = json.dumps(content).encode()
            request.content = ASGIContent(MockReceive([encoded_content]))

        response = await self.app.handle(request)

        return response

    def _prepare_application(self):
        if self.app._service_provider is None:
            self.app.build_services()
            self.app.normalize_handlers()
            self.app.use_controllers()
            self.app.configure_middlewares()
