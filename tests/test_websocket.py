import pytest

from blacksheep.server.websocket import (
    InvalidWebSocketStateError,
    WebSocket,
    WebSocketDisconnectError,
    WebSocketState,
)
from blacksheep.testing.messages import MockReceive, MockSend
from tests.utils.application import FakeApplication


@pytest.fixture
def example_scope():
    return {"type": "websocket"}


@pytest.mark.asyncio
async def test_websocket_connect(example_scope):
    """
    A websocket gets connected when the ASGI server sends a message of type
    'websocket.connect'.
    """
    ws = WebSocket(
        example_scope, MockReceive([{"type": "websocket.connect"}]), MockSend()
    )

    await ws._connect()

    assert ws.client_state == WebSocketState.CONNECTED

    # application state is still connecting because the server did not accept, yet
    assert ws.application_state == WebSocketState.CONNECTING


@pytest.mark.asyncio
async def test_websocket_accept(example_scope):
    """
    A websocket gets fully connected when the ASGI server sends a message of type
    'websocket.connect' and the server accepts the connection.
    """
    mocked_send = MockSend()
    ws = WebSocket(
        example_scope, MockReceive([{"type": "websocket.connect"}]), mocked_send
    )

    await ws.accept()

    assert ws.client_state == WebSocketState.CONNECTED
    assert ws.application_state == WebSocketState.CONNECTED


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
async def test_application_handling_websocket_request_not_found():
    """
    If a client tries to open a WebSocket connection on an endpoint that is not handled,
    the application returns an ASGI message to close the connection.
    """
    app = FakeApplication()
    mock_send = MockSend()
    mock_receive = MockReceive()

    await app({"type": "websocket", "path": "/ws"}, mock_receive, mock_send)

    close_message = mock_send.messages[0]
    assert close_message == {"type": "websocket.close", "code": 1000}


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
    await app({"type": "websocket", "path": "/ws/001"}, mock_receive, mock_send)


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
    await app({"type": "websocket", "path": "/ws"}, mock_receive, mock_send)
