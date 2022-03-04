from enum import Enum
from functools import wraps
from typing import Any, AnyStr, Callable, List, MutableMapping, Optional

from blacksheep.messages import Request
from blacksheep.plugins import json
from blacksheep.server.asgi import get_full_path


class WebSocketState(Enum):
    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2


class MessageMode(Enum):
    TEXT = "text"
    BYTES = "bytes"


class WebSocketError(Exception):
    """Base class for all web sockets errors."""


class InvalidWebSocketStateError(WebSocketError):
    def __init__(
        self,
        *,
        party: str = "client",
        current_state: WebSocketState,
        expected_state: WebSocketState,
    ):
        super().__init__(party, current_state, expected_state)
        self.party = party
        self.current_state = current_state
        self.expected_state = expected_state

    def __str__(self):
        return (
            f"Invalid {self.party} state of the WebSocket connection. "
            f"Expected state: {self.expected_state}. "
            f"Current state: {self.current_state}."
        )


class WebSocketDisconnectError(WebSocketError):
    def __init__(self, code: int = 1000):
        super().__init__(code)
        self.code = code

    def __str__(self):
        return f"The client closed the connection. WebSocket close code: {self.code}."


class WebSocket(Request):
    def __init__(
        self, scope: MutableMapping[str, Any], receive: Callable, send: Callable
    ):
        assert scope["type"] == "websocket"
        super().__init__("GET", get_full_path(scope), list(scope["headers"]))

        self.scope = scope  # type: ignore
        self._receive = self._wrap_receive(receive)
        self._send = send
        self.route_values = {}

        self.client_state = WebSocketState.CONNECTING
        self.application_state = WebSocketState.CONNECTING

    def __repr__(self):
        return f"<WebSocket {self.url.value.decode()}>"

    async def _connect(self) -> None:
        if self.client_state != WebSocketState.CONNECTING:
            raise InvalidWebSocketStateError(
                current_state=self.client_state,
                expected_state=WebSocketState.CONNECTING,
            )

        message = await self._receive()
        assert message["type"] == "websocket.connect"

        self.client_state = WebSocketState.CONNECTED

    async def accept(
        self, headers: Optional[List] = None, subprotocol: str = None
    ) -> None:
        headers = headers or []

        await self._connect()
        self.application_state = WebSocketState.CONNECTED

        message = {
            "type": "websocket.accept",
            "headers": headers,
            "subprotocol": subprotocol,
        }

        await self._send(message)

    async def receive(self) -> MutableMapping[str, AnyStr]:
        if self.application_state != WebSocketState.CONNECTED:
            raise InvalidWebSocketStateError(
                party="application",
                current_state=self.application_state,
                expected_state=WebSocketState.CONNECTED,
            )

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
        self, mode: MessageMode = MessageMode.TEXT
    ) -> MutableMapping[str, Any]:
        message = await self.receive()

        if mode == MessageMode.TEXT:
            return json.loads(message["text"])

        if mode == MessageMode.BYTES:
            return json.loads(message["bytes"].decode())

    async def _send_message(self, message: MutableMapping[str, AnyStr]) -> None:
        if self.client_state != WebSocketState.CONNECTED:
            raise InvalidWebSocketStateError(
                current_state=self.client_state,
                expected_state=WebSocketState.CONNECTED,
            )
        await self._send(message)

    async def send_text(self, data: str) -> None:
        await self._send_message({"type": "websocket.send", "text": data})

    async def send_bytes(self, data: bytes) -> None:
        await self._send_message({"type": "websocket.send", "bytes": data})

    async def send_json(
        self, data: MutableMapping[Any, Any], mode: MessageMode = MessageMode.TEXT
    ):
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
                raise WebSocketDisconnectError(message["code"])

            return message

        return disconnect

    async def close(self, code: int = 1000, reason: Optional[str] = None) -> None:
        await self._send({"type": "websocket.close", "code": code, "reason": reason})
