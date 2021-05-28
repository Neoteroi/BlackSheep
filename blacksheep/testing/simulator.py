import abc
from typing import Dict, Optional
from urllib import parse

from blacksheep.contents import Content
from blacksheep.messages import Request
from blacksheep.server.application import Application
from blacksheep.server.responses import Response
from blacksheep.testing.helpers import get_example_scope


def _create_scope(
    method: str,
    path: str,
    headers: Optional[Dict[str, str]] = None,
    query: Optional[Dict[str, str]] = b"",
) -> Dict:
    """Creates a mocked ASGI scope"""
    if headers is not None:
        headers = [(key.encode(), value.encode()) for key, value in headers.items()]

    if query:
        query = parse.urlencode(query).encode()

    scope = get_example_scope(method, path, extra_headers=headers, query=query)
    return scope


class AbstractTestSimulator:
    """An abstract class for custom Test simulator clients"""

    @abc.abstractmethod
    async def send_request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query: Optional[Dict[str, str]] = b"",
        content: Optional[Content] = None,
    ):
        """Entrypoint for all HTTP methods

        The method is main entrypoint for all TestClient methods
            - get
            - post
            - patch
            - put
            - delete
        Then you can define an own TestClient, with the custom logic.
        """
        pass


class TestSimulator(AbstractTestSimulator):
    """Base Test simulator class

    The class introduces a fast "tests" for your server-side application,
    it means that all incoming requests are mocked.
    """

    def __init__(self, app: Application):
        self.app = app
        self._prepare_application()

    async def send_request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query: Optional[Dict[str, str]] = b"",
        content: Optional[Content] = None,
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
            if not isinstance(content, Content):
                raise ValueError(
                    "The content argument should be an instance of Content class"
                )

            request.content = content

        response = await self.app.handle(request)

        return response

    def _prepare_application(self):
        if self.app._service_provider is None:
            self.app.build_services()
            self.app.normalize_handlers()
            self.app.use_controllers()
            self.app.configure_middlewares()
