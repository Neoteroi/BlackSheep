import abc
from typing import Dict, Optional

from blacksheep.contents import Content
from blacksheep.messages import Request
from blacksheep.server.application import Application
from blacksheep.server.responses import Response
from blacksheep.testing.helpers import get_example_scope

from .helpers import CookiesType, HeadersType, QueryType


def _create_scope(
    method: str,
    path: str,
    headers: HeadersType = None,
    query: QueryType = None,
    cookies: CookiesType = None,
) -> Dict:
    """Creates a mocked ASGI scope"""
    return get_example_scope(
        method, path, extra_headers=headers, query=query, cookies=cookies
    )


class AbstractTestSimulator:
    """An abstract class for custom Test simulator clients"""

    @abc.abstractmethod
    async def send_request(
        self,
        method: str,
        path: str,
        headers: HeadersType = None,
        query: QueryType = None,
        content: Optional[Content] = None,
        cookies: CookiesType = None,
    ) -> Response:
        """Entrypoint for all HTTP methods

        The method is main entrypoint for all TestClient methods
            - get
            - post
            - patch
            - put
            - delete
        Then you can define an own TestClient, with the custom logic.
        """


class TestSimulator(AbstractTestSimulator):
    """Base Test simulator class

    The class introduces a fast "tests" for your server-side application,
    it means that all incoming requests are mocked.
    """

    def __init__(self, app: Application):
        self.app = app
        self._is_started_app()

    async def send_request(
        self,
        method: str,
        path: str,
        headers: HeadersType = None,
        query: QueryType = None,
        content: Optional[Content] = None,
        cookies: CookiesType = None,
    ) -> Response:
        scope = _create_scope(method, path, headers, query, cookies=cookies)
        request = Request.incoming(
            scope["method"],
            scope["raw_path"],
            scope["query_string"],
            scope["headers"],
        )

        request.scope = scope  # type: ignore

        if content is not None:
            if not isinstance(content, Content):
                raise ValueError(
                    "The content argument should be an instance of Content class"
                )

            request.content = content

        response = await self.app.handle(request)

        return response

    def _is_started_app(self):
        assert (
            self.app.started
        ), "The BlackSheep application is not started, use Application.start method"
