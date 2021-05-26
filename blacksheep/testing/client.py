from typing import Any, Dict, Optional

from blacksheep.server.application import Application
from blacksheep.server.responses import Response
from blacksheep.testing.simulator import AbstractTestSimulator, TestSimulator


class TestClient:
    def __init__(
        self, app: Application, test_simulator: Optional[AbstractTestSimulator] = None
    ):
        self._test_simulator = test_simulator or TestSimulator(app)

    async def get(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query: Optional[Dict[str, str]] = b"",
    ) -> Response:
        return await self._test_simulator.send_request(
            method="GET", path=path, headers=headers, query=query, content=None
        )

    async def post(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query: Optional[Dict[str, str]] = b"",
        content: Optional[Dict[str, Any]] = None,
    ) -> Response:
        return await self._test_simulator.send_request(
            method="POST", path=path, headers=headers, query=query, content=content
        )

    async def patch(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query: Optional[Dict[str, str]] = b"",
        content: Optional[Dict[str, Any]] = None,
    ) -> Response:
        return await self._test_simulator.send_request(
            method="PATCH", path=path, headers=headers, query=query, content=content
        )

    async def put(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query: Optional[Dict[str, str]] = b"",
        content: Optional[Dict[str, Any]] = None,
    ) -> Response:
        return await self._test_simulator.send_request(
            method="PUT", path=path, headers=headers, query=query, content=content
        )

    async def delete(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query: Optional[Dict[str, str]] = b"",
        content: Optional[Dict[str, Any]] = None,
    ) -> Response:
        return await self._test_simulator.send_request(
            method="DELETE", path=path, headers=headers, query=query, content=content
        )
