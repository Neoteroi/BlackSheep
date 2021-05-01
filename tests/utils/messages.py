import asyncio


class MockMessage:
    def __init__(self, value):
        self.value = value


class MockReceive:
    def __init__(self, messages=None):
        self.messages = messages or []
        self.index = 0

    async def __call__(self):
        try:
            message = self.messages[self.index]
        except IndexError:
            message = b""
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
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)
