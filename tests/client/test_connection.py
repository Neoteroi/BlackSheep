import asyncio
from asyncio import TimeoutError
from typing import AsyncIterable, List

from httptools.parser.errors import HttpParserCallbackError, HttpParserError
from blacksheep import JSONContent, Request, StreamedContent

import pytest

from blacksheep.client.connection import (
    ClientConnection,
    ConnectionClosedError,
    IncomingContent,
    InvalidResponseFromServer,
    UpgradeResponse,
)
from blacksheep.client.pool import ClientConnectionPool


def get_example_headers():
    return [
        (b"host", b"127.0.0.1:8000"),
        (
            b"user-agent",
            (
                b"Mozilla/5.0 (X11; Ubuntu; Linux x86_64; "
                b"rv:63.0) Gecko/20100101 Firefox/63.0"
            ),
        ),
        (
            b"accept",
            (b"text/html,application/xhtml+xml," b"application/xml;q=0.9,*/*;q=0.8"),
        ),
        (b"accept-language", b"en-US,en;q=0.9,it-IT;q=0.8,it;q=0.7"),
        (b"accept-encoding", b"gzip, deflate"),
        (b"connection", b"keep-alive"),
        (b"upgrade-insecure-requests", b"1"),
    ]


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def pool(event_loop):
    pool = ClientConnectionPool(event_loop, b"http", b"foo.com", 80, None, max_size=2)
    yield pool
    pool.dispose()


class FakeParser:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def get_status_code(self) -> int:
        return self.status_code

    def should_keep_alive(self) -> bool:
        return False


class FakeTransport:
    def __init__(self) -> None:
        self.messages: List[bytes] = []

    def write(self, message: bytes) -> None:
        self.messages.append(message)

    def close(self) -> None:
        pass


@pytest.fixture()
def connection(pool):
    connection = ClientConnection(pool.loop, pool)
    connection.parser = FakeParser(200)
    yield connection


def test_connection_pause_resume(connection):
    assert connection.writing_paused is False
    connection.pause_writing()
    assert connection.writing_paused is True
    connection.resume_writing()
    assert connection.writing_paused is False


def test_connection_has_a_response_when_headers_are_complete(
    connection: ClientConnection,
):
    connection.headers = get_example_headers()

    connection.on_headers_complete()

    # when headers are complete, the connection must have a response
    assert connection.response is not None
    response = connection.response

    for name, value in get_example_headers():
        assert response.headers.get_single(name) == value


@pytest.mark.asyncio
async def test_connection_send_throws_if_closed(connection: ClientConnection):
    connection.open = False

    with pytest.raises(ConnectionClosedError):
        await connection.send(Request("GET", b"/", None))


@pytest.mark.asyncio
async def test_connection_handle_upgrades(
    connection: ClientConnection,
):
    connection.headers = get_example_headers()
    connection.parser = FakeParser(101)
    connection.transport = object()

    connection.on_headers_complete()

    with pytest.raises(UpgradeResponse) as upgrade_response:
        await connection._wait_response()

    assert upgrade_response.value.response is connection.response
    assert upgrade_response.value.transport is connection.transport
    assert connection._upgraded is True


@pytest.mark.asyncio
async def test_connection_handle_expect_100_continue_and_1xx(
    connection: ClientConnection,
):
    # Arrange
    connection.open = True
    connection.headers = get_example_headers()
    connection.parser = FakeParser(100)
    connection.transport = FakeTransport()

    request = Request(
        "POST",
        b"/",
        headers=[(b"content-type", b"application/json"), (b"expect", b"100-continue")],
    ).with_content(JSONContent({"id": "1", "name": "foo"}))

    # Arrange future response...
    connection.headers = get_example_headers()
    connection.parser = FakeParser(100)
    # trick: simulate a complete response before the request is sent;
    # here is legit because we are simulating a proper scenario
    connection.on_headers_complete()

    try:
        await asyncio.wait_for(connection.send(request), 0.01)
    except TimeoutError:
        pass

    # The first message must include only headers without body,
    # the second the body (received after the 100 response arrived)

    assert (
        connection.transport.messages[0]
        == b"POST / HTTP/1.1\r\ncontent-type: application/json\r\nexpect: 100-continue\r\n\r\n"
    )
    assert connection.transport.messages[1] == b'{"id":"1","name":"foo"}'


class FakePoolThrowingOnRelease(ClientConnectionPool):
    def try_return_connection(self, connection: ClientConnection) -> None:
        raise Exception("Crash")


def test_closed_connection_does_not_return_to_pool(event_loop):
    pool = FakePoolThrowingOnRelease(
        event_loop, b"http", b"foo.com", 80, None, max_size=2
    )
    connection = ClientConnection(pool.loop, pool)
    connection.open = False
    connection.release()


def test_upgraded_connection_does_not_return_to_pool(event_loop):
    pool = FakePoolThrowingOnRelease(
        event_loop, b"http", b"foo.com", 80, None, max_size=2
    )
    connection = ClientConnection(pool.loop, pool)
    connection._upgraded = True
    connection.release()


def test_connection_gets_closed_on_callback_error(connection):
    class FakeParser:
        def feed_data(self, data: bytes):
            raise HttpParserCallbackError()

    connection.parser = FakeParser()

    with pytest.raises(HttpParserCallbackError):
        connection.data_received(b"boom")

    assert connection.open is False


def test_connection_throws_invalid_response_from_server_on_parser_error(connection):
    class FakeParser:
        def feed_data(self, data: bytes):
            raise HttpParserError()

    connection.parser = FakeParser()

    with pytest.raises(InvalidResponseFromServer):
        connection.data_received(b"boom")

    assert connection.open is False


@pytest.mark.asyncio
async def test_connection_stops_sending_body_if_server_returns_response(connection):
    async def dummy_body_generator() -> AsyncIterable[bytes]:
        for i in range(5):
            await asyncio.sleep(0.01)
            yield str(i).encode()

            if i > 2:
                # simulate getting a bad request response from the server:
                connection.headers = get_example_headers()
                connection.parser = FakeParser(400)
                connection.on_headers_complete()
                connection.on_message_complete()

    request = Request("POST", b"https://localhost:3000/foo", []).with_content(
        StreamedContent(b"text/plain", dummy_body_generator)
    )
    fake_transport = FakeTransport()
    connection.open = True
    connection.transport = fake_transport
    response = await connection.send(request)

    assert response.status == 400
    # NB: connection stopped writing to transport before the end of the body:
    assert fake_transport.messages == [
        b"POST /foo HTTP/1.1\r\nhost: localhost\r\ncontent-type: "
        + b"text/plain\r\ntransfer-encoding: chunked\r\n\r\n",
        b"1\r\n0\r\n",
        b"1\r\n1\r\n",
        b"1\r\n2\r\n",
        b"1\r\n3\r\n",
    ]


@pytest.mark.asyncio
async def test_on_connection_lost_send_throws(connection):
    async def dummy_body_generator() -> AsyncIterable[bytes]:
        for i in range(5):
            await asyncio.sleep(0.01)
            yield str(i).encode()

            if i > 2:
                # simulate connection lost
                connection.connection_lost(None)

    request = Request("POST", b"https://localhost:3000/foo", []).with_content(
        StreamedContent(b"text/plain", dummy_body_generator)
    )
    fake_transport = FakeTransport()
    connection.open = True
    connection.transport = fake_transport

    with pytest.raises(ConnectionClosedError):
        await connection.send(request)


@pytest.mark.asyncio
async def test_on_writing_paused_awaits(connection):
    async def dummy_body_generator() -> AsyncIterable[bytes]:
        for i in range(5):
            await asyncio.sleep(0.01)
            yield str(i).encode()

            if i > 2:
                # simulate connection pause
                connection.pause_writing()

    request = Request("POST", b"https://localhost:3000/foo", []).with_content(
        StreamedContent(b"text/plain", dummy_body_generator)
    )
    fake_transport = FakeTransport()
    connection.open = True
    connection.transport = fake_transport

    try:
        await asyncio.wait_for(connection.send(request), 0.1)
    except TimeoutError:
        pass

    assert connection.writing_paused is True
    assert fake_transport.messages == [
        b"POST /foo HTTP/1.1\r\nhost: localhost\r\ncontent-type: "
        + b"text/plain\r\ntransfer-encoding: chunked\r\n\r\n",
        b"1\r\n0\r\n",
        b"1\r\n1\r\n",
        b"1\r\n2\r\n",
        b"1\r\n3\r\n",
    ]


def test_connection_throws_for_invalid_content_length(connection):
    connection.headers = get_example_headers()
    connection.headers.append((b"Content-Length", b"NOT_A_NUMBER"))
    connection.headers.append((b"Content-Type", b"text/html"))
    connection.parser = FakeParser(200)

    with pytest.raises(InvalidResponseFromServer):
        connection.on_headers_complete()


@pytest.mark.asyncio
async def test_connection_handle_chunked_transfer_encoding(
    connection: ClientConnection,
):
    # Arrange fake response...
    connection.headers = get_example_headers()
    connection.headers.append((b"content-type", b"text/plain"))
    connection.headers.append((b"transfer-encoding", b"chunked"))
    connection.on_headers_complete()

    # connection is going to wait for a response:
    assert connection.response is not None
    assert connection.response.content is not None
    assert isinstance(connection.response.content, IncomingContent)
