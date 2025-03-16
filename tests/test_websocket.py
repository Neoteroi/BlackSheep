import pytest

from blacksheep.server.bindings import FromHeader
from blacksheep.server.websocket import (
    InvalidWebSocketStateError,
    MessageMode,
    WebSocket,
    WebSocketDisconnectError,
    WebSocketState,
    format_reason,
)
from blacksheep.testing import TestClient
from blacksheep.testing.messages import MockReceive, MockSend
from tests.utils.application import FakeApplication


@pytest.fixture
def example_scope():
    return {
        "type": "websocket",
        "path": "/ws",
        "query_string": "",
        "headers": [(b"upgrade", b"websocket")],
    }


def test_websocket_repr(example_scope):
    ws = WebSocket(example_scope, MockReceive([]), MockSend())

    assert str(ws) == "<WebSocket /ws>"


async def test_connect_raises_if_not_connecting(example_scope):
    ws = WebSocket(
        example_scope, MockReceive([{"type": "websocket.connect"}]), MockSend()
    )

    ws.client_state = WebSocketState.CONNECTED

    with pytest.raises(InvalidWebSocketStateError) as error:
        await ws.accept()

    assert error.value.current_state == WebSocketState.CONNECTED
    assert error.value.expected_state == WebSocketState.CONNECTING

    assert str(error.value) == (
        f"Invalid {error.value.party} state of the WebSocket connection. "
        f"Expected state: {error.value.expected_state}. "
        f"Current state: {error.value.current_state}."
    )


async def test_websocket_accept(example_scope):
    """
    A websocket gets fully connected when the ASGI server sends a message of type
    'websocket.connect' and the server accepts the connection.
    """
    ws = WebSocket(
        example_scope, MockReceive([{"type": "websocket.connect"}]), MockSend()
    )

    await ws.accept()

    assert ws.client_state == WebSocketState.CONNECTED
    assert ws.application_state == WebSocketState.CONNECTED


async def test_websocket_receive_text(example_scope):
    """
    A first message is received when the underlying ASGI server first sends a
    'websocket.connect' message, then a content message.
    """
    ws = WebSocket(
        example_scope,
        MockReceive(
            [
                {"type": "websocket.connect"},
                {"type": "websocket.receive", "text": "Lorem ipsum dolor sit amet"},
            ]
        ),
        MockSend(),
    )

    await ws.accept()

    message = await ws.receive_text()
    assert message == "Lorem ipsum dolor sit amet"


async def test_websocket_receive_bytes(example_scope):
    """
    A first message is received when the underlying ASGI server first sends a
    'websocket.connect' message, then a content message.
    """
    ws = WebSocket(
        example_scope,
        MockReceive(
            [
                {"type": "websocket.connect"},
                {"type": "websocket.receive", "bytes": b"Lorem ipsum dolor sit amet"},
            ]
        ),
        MockSend(),
    )

    await ws.accept()

    message = await ws.receive_bytes()
    assert message == b"Lorem ipsum dolor sit amet"


async def test_websocket_receive_json(example_scope):
    """
    A first message is received when the underlying ASGI server first sends a
    'websocket.connect' message, then a content message.
    """
    ws = WebSocket(
        example_scope,
        MockReceive(
            [
                {"type": "websocket.connect"},
                {"type": "websocket.receive", "text": '{"message": "Lorem ipsum"}'},
            ]
        ),
        MockSend(),
    )

    await ws.accept()

    message = await ws.receive_json()
    assert message == {"message": "Lorem ipsum"}


async def test_websocket_receive_json_from_bytes(example_scope):
    """
    A first message is received when the underlying ASGI server first sends a
    'websocket.connect' message, then a content message.
    """
    ws = WebSocket(
        example_scope,
        MockReceive(
            [
                {"type": "websocket.connect"},
                {"type": "websocket.receive", "bytes": b'{"message": "Lorem ipsum"}'},
            ]
        ),
        MockSend(),
    )

    await ws.accept()

    message = await ws.receive_json(mode=MessageMode.BYTES)
    assert message == {"message": "Lorem ipsum"}


async def test_websocket_send_text(example_scope):
    """
    A message is sent by the server to clients, by sending a message to the underlying
    ASGI server with type "websocket.send" and a "text" or "bytes" property.
    """
    mocked_send = MockSend()
    ws = WebSocket(
        example_scope,
        MockReceive([{"type": "websocket.connect"}]),
        mocked_send,
    )

    await ws.accept()

    await ws.send_text("Lorem ipsum dolor sit amet")

    assert len(mocked_send.messages) > 0
    message = mocked_send.messages[-1]

    assert message.get("text") == "Lorem ipsum dolor sit amet"
    assert message.get("type") == "websocket.send"


async def test_websocket_send_bytes(example_scope):
    """
    A message is sent by the server to clients, by sending a message to the underlying
    ASGI server with type "websocket.send" and a "text" or "bytes" property.
    """
    mocked_send = MockSend()
    ws = WebSocket(
        example_scope,
        MockReceive([{"type": "websocket.connect"}]),
        mocked_send,
    )

    await ws.accept()

    await ws.send_bytes(b"Lorem ipsum dolor sit amet")

    assert len(mocked_send.messages) > 0
    message = mocked_send.messages[-1]

    assert message.get("bytes") == b"Lorem ipsum dolor sit amet"
    assert message.get("type") == "websocket.send"


async def test_websocket_send_json(example_scope):
    """
    A message is sent by the server to clients, by sending a message to the underlying
    ASGI server with type "websocket.send" and a "text" or "bytes" property.
    """
    mocked_send = MockSend()
    ws = WebSocket(
        example_scope,
        MockReceive([{"type": "websocket.connect"}]),
        mocked_send,
    )

    await ws.accept()

    await ws.send_json({"message": "Lorem ipsum dolor sit amet"})

    assert len(mocked_send.messages) > 0
    message = mocked_send.messages[-1]

    assert message.get("text") == '{"message":"Lorem ipsum dolor sit amet"}'
    assert message.get("type") == "websocket.send"


async def test_websocket_send_json_as_bytes(example_scope):
    """
    A message is sent by the server to clients, by sending a message to the underlying
    ASGI server with type "websocket.send" and a "text" or "bytes" property.
    """
    mocked_send = MockSend()
    ws = WebSocket(
        example_scope,
        MockReceive([{"type": "websocket.connect"}]),
        mocked_send,
    )

    await ws.accept()

    await ws.send_json({"message": "Lorem ipsum dolor sit amet"}, MessageMode.BYTES)

    assert len(mocked_send.messages) > 0
    message = mocked_send.messages[-1]

    assert message.get("bytes") == b'{"message":"Lorem ipsum dolor sit amet"}'
    assert message.get("type") == "websocket.send"


async def test_connecting_websocket_raises_for_receive(example_scope):
    ws = WebSocket(example_scope, MockReceive(), MockSend())

    assert ws.client_state == WebSocketState.CONNECTING

    with pytest.raises(InvalidWebSocketStateError) as error:
        await ws.receive()

    assert error.value.current_state == WebSocketState.CONNECTING
    assert error.value.expected_state == WebSocketState.CONNECTED

    assert str(error.value) == (
        f"Invalid {error.value.party} state of the WebSocket connection. "
        f"Expected state: {error.value.expected_state}. "
        f"Current state: {error.value.current_state}."
    )


async def test_connecting_websocket_raises_for_send(example_scope):
    ws = WebSocket(example_scope, MockReceive(), MockSend())

    assert ws.client_state == WebSocketState.CONNECTING

    with pytest.raises(InvalidWebSocketStateError) as error:
        await ws.send_text("Error")

    assert error.value.current_state == WebSocketState.CONNECTING
    assert error.value.expected_state == WebSocketState.CONNECTED

    assert str(error.value) == (
        f"Invalid {error.value.party} state of the WebSocket connection. "
        f"Expected state: {error.value.expected_state}. "
        f"Current state: {error.value.current_state}."
    )


async def test_websocket_raises_for_receive_when_closed_by_client(example_scope):
    """
    If the underlying ASGI server sends a message of type "websocket.disconnect",
    it means that the client disconnected.
    """
    ws = WebSocket(
        example_scope,
        MockReceive(
            [
                {"type": "websocket.connect"},
                {"type": "websocket.disconnect", "code": 500},
            ]
        ),
        MockSend(),
    )

    await ws.accept()

    with pytest.raises(WebSocketDisconnectError) as error:
        await ws.receive()

    assert error.value.code == 500

    assert str(error.value) == (
        f"The client closed the connection. WebSocket close code: {error.value.code}."
    )


async def test_application_handling_websocket_request_not_found():
    """
    If a client tries to open a WebSocket connection on an endpoint that is not handled,
    the application returns an ASGI message to close the connection.
    """
    app = FakeApplication()
    await app.start()

    client = TestClient(app)
    test_websocket = client.websocket_connect("/ws")
    await test_websocket.send({"type": "websocket.connect"})
    close_message = await test_websocket.receive()

    assert close_message == {"type": "websocket.close", "reason": None, "code": 1000}


async def test_application_handling_proper_websocket_request():
    """
    If a client tries to open a WebSocket connection on an endpoint that is handled,
    the application websocket handler is called.
    """
    app = FakeApplication()

    @app.router.ws("/ws/{foo}")
    async def websocket_handler(websocket, foo):
        assert isinstance(websocket, WebSocket)
        assert websocket.application_state == WebSocketState.CONNECTING
        assert websocket.client_state == WebSocketState.CONNECTING

        assert foo == "001"

        await websocket.accept()

    await app.start()
    client = TestClient(app)
    async with client.websocket_connect("/ws/001"):
        pass


async def test_application_handling_proper_websocket_request_with_query():
    app = FakeApplication()

    @app.router.ws("/ws/{foo}")
    async def websocket_handler(websocket: WebSocket, foo, from_query: int):
        assert isinstance(websocket, WebSocket)
        assert websocket.application_state == WebSocketState.CONNECTING
        assert websocket.client_state == WebSocketState.CONNECTING

        assert foo == "001"
        assert from_query == 200

        await websocket.accept()

    await app.start()
    client = TestClient(app)
    async with client.websocket_connect("/ws/001", query="from_query=200"):
        pass


async def test_application_handling_proper_websocket_request_header_binding():
    app = FakeApplication()

    class UpgradeHeader(FromHeader[str]):
        name = "Upgrade"

    @app.router.ws("/ws")
    async def websocket_handler(websocket: WebSocket, connect_header: UpgradeHeader):
        assert connect_header.value == "websocket"
        await websocket.accept()

    await app.start()
    client = TestClient(app)
    async with client.websocket_connect("/ws", headers={"upgrade": "websocket"}):
        pass


async def test_application_websocket_binding_by_type_annotation():
    """
    This test verifies that the WebSocketBinder can bind a WebSocket by type annotation.
    """
    app = FakeApplication()

    @app.router.ws("/ws")
    async def websocket_handler(my_ws: WebSocket):
        assert isinstance(my_ws, WebSocket)
        assert my_ws.application_state == WebSocketState.CONNECTING
        assert my_ws.client_state == WebSocketState.CONNECTING

        await my_ws.accept()

    await app.start()
    client = TestClient(app)
    async with client.websocket_connect("/ws"):
        pass


async def test_websocket_handler_must_not_return():
    """
    This test verifies that normalized request handlers handling WebSockets are not
    normalized to return an instance of Response.
    """
    app = FakeApplication()

    @app.router.ws("/ws")
    async def websocket_handler(my_ws: WebSocket):
        pass

    await app.start()

    # Because the defined handler is asynchronous and accepts a WebSocket,
    # it should not be normalized and kept as-is
    for route in app.router:
        assert route.handler is websocket_handler
        assert await route.handler(...) is None


async def test_testwebsocket_closing():
    """
    This test verifies that websocket.disconnect is sent by TestWebSocket
    """
    app = FakeApplication()
    disconnected = False

    @app.router.ws("/ws")
    async def websocket_handler(my_ws: WebSocket):
        await my_ws.accept()
        try:
            await my_ws.receive()
        except WebSocketDisconnectError:
            nonlocal disconnected
            disconnected = True

    await app.start()
    client = TestClient(app)
    async with client.websocket_connect("/ws"):
        pass
    await client.websocket_all_closed()
    assert disconnected is True


async def test_testwebsocket_send_receive_methods():
    """
    This test verifies that TestWebSocket sends and receives different formats
    """
    app = FakeApplication()

    @app.router.ws("/ws")
    async def websocket_handler(my_ws: WebSocket):
        await my_ws.accept()
        await my_ws.send_text("send")
        await my_ws.send_json({"send": "test"})
        await my_ws.send_bytes(b"send")
        received = await my_ws.receive_text()
        assert received == "received"
        received = await my_ws.receive_json()
        assert received == {"received": "test"}
        received = await my_ws.receive_bytes()
        assert received == b"received"
        await my_ws.close()

    await app.start()
    client = TestClient(app)
    async with client.websocket_connect("/ws") as ws:
        received = await ws.receive_text()
        assert received == "send"
        received = await ws.receive_json()
        assert received == {"send": "test"}
        received = await ws.receive_bytes()
        assert received == b"send"

        await ws.send_text("received")
        await ws.send_json({"received": "test"})
        await ws.send_text(b"received")


LONG_REASON = "WRY" * 41
QIN = "秦"  # Qyn dynasty in Chinese, 3 bytes.
TOO_LONG_REASON = QIN * 42
TOO_LONG_REASON_TRUNC = TOO_LONG_REASON[:40] + "..."


@pytest.mark.parametrize(
    "inp,out",
    [
        ("Short reason", "Short reason"),
        (LONG_REASON, LONG_REASON),
        (TOO_LONG_REASON, TOO_LONG_REASON_TRUNC),
    ],
)
def test_format_reason(inp, out):
    assert format_reason(inp) == out
