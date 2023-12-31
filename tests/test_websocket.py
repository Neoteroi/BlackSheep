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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_application_handling_websocket_request_not_found(example_scope):
    """
    If a client tries to open a WebSocket connection on an endpoint that is not handled,
    the application returns an ASGI message to close the connection.
    """
    app = FakeApplication()
    mock_send = MockSend()
    mock_receive = MockReceive()

    await app(example_scope, mock_receive, mock_send)

    close_message = mock_send.messages[0]
    assert close_message == {"type": "websocket.close", "reason": None, "code": 1000}


@pytest.mark.asyncio
async def test_application_handling_proper_websocket_request():
    """
    If a client tries to open a WebSocket connection on an endpoint that is handled,
    the application websocket handler is called.
    """
    app = FakeApplication()
    mock_send = MockSend()
    mock_receive = MockReceive([{"type": "websocket.connect"}])

    @app.router.ws("/ws/{foo}")
    async def websocket_handler(websocket, foo):
        assert isinstance(websocket, WebSocket)
        assert websocket.application_state == WebSocketState.CONNECTING
        assert websocket.client_state == WebSocketState.CONNECTING

        assert foo == "001"

        await websocket.accept()

    await app.start()
    await app(
        {"type": "websocket", "path": "/ws/001", "query_string": "", "headers": []},
        mock_receive,
        mock_send,
    )


@pytest.mark.asyncio
async def test_application_handling_proper_websocket_request_with_query():
    app = FakeApplication()
    mock_send = MockSend()
    mock_receive = MockReceive([{"type": "websocket.connect"}])

    @app.router.ws("/ws/{foo}")
    async def websocket_handler(websocket, foo, from_query: int):
        assert isinstance(websocket, WebSocket)
        assert websocket.application_state == WebSocketState.CONNECTING
        assert websocket.client_state == WebSocketState.CONNECTING

        assert foo == "001"
        assert from_query == 200

        await websocket.accept()

    await app.start()
    await app(
        {
            "type": "websocket",
            "path": "/ws/001",
            "query_string": b"from_query=200",
            "headers": [],
        },
        mock_receive,
        mock_send,
    )


@pytest.mark.asyncio
async def test_application_handling_proper_websocket_request_header_binding(
    example_scope,
):
    app = FakeApplication()
    mock_send = MockSend()
    mock_receive = MockReceive([{"type": "websocket.connect"}])

    class UpgradeHeader(FromHeader[str]):
        name = "Upgrade"

    called = False

    @app.router.ws("/ws")
    async def websocket_handler(connect_header: UpgradeHeader):
        assert connect_header.value == "websocket"

        nonlocal called
        called = True

    await app.start()
    await app(example_scope, mock_receive, mock_send)
    assert called is True


@pytest.mark.asyncio
async def test_application_websocket_binding_by_type_annotation():
    """
    This test verifies that the WebSocketBinder can bind a WebSocket by type annotation.
    """
    app = FakeApplication()
    mock_send = MockSend()
    mock_receive = MockReceive([{"type": "websocket.connect"}])

    @app.router.ws("/ws")
    async def websocket_handler(my_ws: WebSocket):
        assert isinstance(my_ws, WebSocket)
        assert my_ws.application_state == WebSocketState.CONNECTING
        assert my_ws.client_state == WebSocketState.CONNECTING

        await my_ws.accept()

    await app.start()
    await app(
        {"type": "websocket", "path": "/ws", "query_string": "", "headers": []},
        mock_receive,
        mock_send,
    )


@pytest.mark.asyncio
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
