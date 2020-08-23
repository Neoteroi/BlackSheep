import asyncio


class MockContext:
    def __init__(self):
        self.connections = []


class MockProtocol(asyncio.Protocol):
    def __init__(self, context: MockContext):
        self.context = context
        context.connections.append(self)

    def data_received(self, data):
        pass

    def eof_received(self):
        pass

    def connection_made(self, transport):
        pass

    def connection_lost(self, exc):
        pass

    def pause_writing(self):
        pass

    def resume_writing(self):
        pass
