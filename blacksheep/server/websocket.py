import json
from enum import Enum
from functools import wraps
from typing import Any, AnyStr, Callable, List, MutableMapping, Optional


class WebSocketDisconnect(Exception):
    def __init__(self, code: int = 1000):
        self.code = code


class WebSocketState(Enum):
    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2


class MessageMode(str, Enum):
    TEXT = "text"
    BYTES = "bytes"


class WebSocket:
    def __init__(
            self,
            scope: MutableMapping[str, Any],
            receive: Callable,
            send: Callable
    ):
        assert scope["type"] == "websocket"

        self._scope = scope
        self._receive = self._wrap_receive(receive)
        self._send = send
        self.route_values = {}

        self.client_state = WebSocketState.CONNECTING
        self.application_state = WebSocketState.CONNECTING

    async def connect(self) -> None:
        message = await self._receive()
        assert message["type"] == "websocket.connect"

        self.client_state = WebSocketState.CONNECTED

    async def accept(
            self,
            headers: Optional[List] = None,
            subprotocol: str = None
    ) -> None:
        assert self.client_state == WebSocketState.CONNECTING
        await self.connect()

        headers = headers or []
        self.application_state = WebSocketState.CONNECTED

        message = {
            "type": "websocket.accept",
            "headers": headers,
            "subprotocol": subprotocol
        }

        await self._send(message)

    async def receive(self) -> MutableMapping[str, AnyStr]:
        assert self.application_state == WebSocketState.CONNECTED

        message = await self._receive()
        assert message["type"] == "websocket.receive"

        return message

    async def receive_text(self) -> str:
        message = await self.receive()
        return message["text"]

    async def receive_bytes(self) -> bytes:
        message = await self.receive()
        return message["bytes"]

    async def receive_json(
            self,
            mode: str = MessageMode.TEXT
    ) -> MutableMapping[str, Any]:
        assert mode in list(MessageMode)
        message = await self.receive()

        if mode == MessageMode.TEXT:
            return json.loads(message["text"])

        if mode == MessageMode.BYTES:
            return json.loads(message["bytes"].decode())

    async def send(self, message: MutableMapping[str, AnyStr]) -> None:
        assert self.client_state == WebSocketState.CONNECTED
        await self._send(message)

    async def send_text(self, data: str) -> None:
        await self.send({
            "type": "websocket.send",
            "text": data
        })

    async def send_bytes(self, data: bytes) -> None:
        await self.send({
            "type": "websocket.send",
            "bytes": data
        })

    async def send_json(
            self,
            data: MutableMapping[Any, Any],
            mode: str = MessageMode.TEXT
    ):
        assert mode in list(MessageMode)
        text = json.dumps(data)

        if mode == MessageMode.TEXT:
            return await self.send_text(text)

        if mode == MessageMode.BYTES:
            return await self.send_bytes(text.encode())

    def _wrap_receive(self, _receive: Callable):
        @wraps(_receive)
        async def disconnect():
            message = await _receive()

            if message["type"] == "websocket.disconnect":
                self.application_state = self.client_state = WebSocketState.DISCONNECTED
                raise WebSocketDisconnect(message["code"])

            return message
        return disconnect

    async def close(self, code: int = 1000) -> None:
        await self._send({
            "type": "websocket.close",
            "code": code
        })
