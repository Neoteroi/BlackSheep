"""These classes implement the interface used by BlackSheep HTTP client implementation, to simplify testing on the
ClientSession object; including handling of connections and requests timeouts; redirects, etc."""

import asyncio


class FakeConnection:
    def __init__(self, fake_responses):
        self.fake_responses = fake_responses
        self.sleep_for = 0.001
        self._iter = iter(fake_responses)

    async def send(self, request):
        await asyncio.sleep(self.sleep_for)
        try:
            return next(self._iter)
        except StopIteration:
            self._iter = iter(self.fake_responses)
            return next(self._iter)

    def close(self):
        pass


class FakePool:
    def __init__(self, fake_connection: FakeConnection, delay=0.001):
        self.connection = fake_connection
        self.sleep_for = delay

    async def get_connection(self):
        await asyncio.sleep(self.sleep_for)
        return self.connection


class FakePools:
    def __init__(self, fake_responses):
        self.fake_responses = fake_responses
        self.pool = FakePool(FakeConnection(self.fake_responses))

    def get_pool(self, scheme, host, port, ssl):
        return self.pool

    def dispose(self):
        pass
