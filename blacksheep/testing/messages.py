import asyncio
from typing import Any, Dict, List, Optional, Union


class MockMessage:
    """
    Class used to mock an exact message from an ASGI framework.
    """

    def __init__(self, value: Dict[str, Any]):
        self.value = value


MessageType = Union[MockMessage, bytes, Dict[str, Any]]


class MockReceive:
    """
    Class used to mock the messages received by an ASGI framework and passed to the
    dependant web framework.

    Example:

        MockReceive([b'{"error":"access_denied"}'])

    Simulates the ASGI server sending this kind of message:

        {
            "body": b'{"error":"access_denied"}',
            "type": "http.message",
            "more_body": False
        }
    """

    def __init__(self, messages: Optional[List[MessageType]] = None):
        self.messages = messages or []
        self.index = 0

    async def __call__(self):
        try:
            message = self.messages[self.index]
        except IndexError:
            message = b""
        if isinstance(message, dict):
            return message
        if isinstance(message, MockMessage):
            return message.value
        self.index += 1
        await asyncio.sleep(0)
        return {
            "body": message,
            "type": "http.message",
            "more_body": False
            if (len(self.messages) == self.index or not message)
            else True,
        }


class MockSend:
    """
    Class used to mock the `send` calls from an ASGI framework.
    Use this class to inspect the messages sent by the framework.
    """

    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)
