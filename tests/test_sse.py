import pytest

from blacksheep.contents import ServerSentEvent
from blacksheep.server.sse import ServerSentEventsResponse


@pytest.mark.asyncio
async def test_server_sent_events_response_streams_events_1():
    # Arrange: create a simple events provider
    async def events_provider():
        yield ServerSentEvent(data={"message": "hello"}, event="greeting", id="1")
        yield ServerSentEvent(data={"message": "world"}, event="greeting", id="2")

    response = ServerSentEventsResponse(events_provider)
    content = response.content
    assert content is not None
    # Collect all bytes from the streamed content
    result = b""
    async for chunk in content.get_parts():  # type: ignore
        result += chunk
    # Check the output contains the expected SSE format
    assert b"id: 1\n" in result
    assert b"event: greeting\n" in result
    assert b'data: {"message":"hello"}\n' in result
    assert b"id: 2\n" in result
    assert b'data: {"message":"world"}\n' in result
    assert content.type == b"text/event-stream"


@pytest.mark.asyncio
async def test_server_sent_events_response_streams_events_2():
    # Arrange: create a simple events provider
    async def events_provider():
        yield ServerSentEvent(data="hello", event="greeting", id="1")
        yield ServerSentEvent(data="world", event="greeting", id="2")

    response = ServerSentEventsResponse(events_provider)
    content = response.content
    assert content is not None
    # Collect all bytes from the streamed content
    result = b""
    async for chunk in content.get_parts():  # type: ignore
        result += chunk
    # Check the output contains the expected SSE format
    assert b"id: 1\n" in result
    assert b"event: greeting\n" in result
    assert b'data: "hello"\n' in result
    assert b"id: 2\n" in result
    assert b'data: "world"\n' in result
    assert content.type == b"text/event-stream"


@pytest.mark.asyncio
async def test_server_sent_events_response_streams_events_3():
    # Arrange: create a simple events provider
    async def events_provider():
        yield ServerSentEvent(data="hello", event="greeting", id="1")
        yield ServerSentEvent(data="world", event="greeting", id="2")

    response = ServerSentEventsResponse(events_provider)
    content = response.content
    assert content is not None
    # Collect all bytes from the streamed content
    result = b""
    async for chunk in content.get_parts():  # type: ignore
        result += chunk
    # Check the output contains the expected SSE format
    assert b"id: 1\n" in result
    assert b"event: greeting\n" in result
    assert b'data: "hello"\n' in result
    assert b"id: 2\n" in result
    assert b'data: "world"\n' in result
    assert content.type == b"text/event-stream"
