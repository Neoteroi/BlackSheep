from __future__ import annotations

import asyncio
from typing import Any, AnyStr, MutableMapping

from blacksheep.settings.json import json_settings


class TestWebSocket:
    def __init__(self):
        self.send_queue = asyncio.Queue()
        self.receive_queue = asyncio.Queue()

    async def _send(self, data: MutableMapping[str, Any]) -> None:
        await self.send_queue.put(data)

    async def _receive(self) -> MutableMapping[str, AnyStr]:
        return await self.receive_queue.get()

    async def send(self, data: MutableMapping[str, Any]) -> None:
        await self.receive_queue.put(data)

    async def send_text(self, data: str) -> None:
        await self.send({"type": "websocket.send", "text": data})

    async def send_bytes(self, data: bytes) -> None:
        await self.send({"type": "websocket.send", "bytes": data})

    async def send_json(self, data: MutableMapping[Any, Any]) -> None:
        await self.send(
            {
                "type": "websocket.send",
                "text": json_settings.dumps(data),
            }
        )

    async def receive(self) -> MutableMapping[str, AnyStr]:
        return await self.send_queue.get()

    async def receive_text(self) -> str:
        data = await self.receive()
        assert data["type"] == "websocket.send"
        return data["text"]

    async def receive_bytes(self) -> bytes:
        data = await self.receive()
        assert data["type"] == "websocket.send"
        return data["bytes"]

    async def receive_json(self) -> MutableMapping[str, Any]:
        data = await self.receive()
        assert data["type"] == "websocket.send"
        return json_settings.loads(data["text"])

    async def __aenter__(self) -> TestWebSocket:
        await self.send({"type": "websocket.connect"})
        received = await self.receive()
        assert received.get("type") == "websocket.accept"
        return self

    async def __aexit__(self, exc_type, exc_value, exc_tb) -> None:
        await self.send(
            {
                "type": "websocket.disconnect",
                "code": 1000,
                "reason": "TestWebSocket context closed",
            },
        )
