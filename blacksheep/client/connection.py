import ssl
import asyncio
SECURE_SSLCONTEXT = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
SECURE_SSLCONTEXT.check_hostname = True

INSECURE_SSLCONTEXT = ssl.SSLContext()
INSECURE_SSLCONTEXT.check_hostname = False


class ConnectionClosedError(Exception):
    pass


class HttpConnection(asyncio.Protocol):

    def __init__(self, loop, pool):
        self.loop = loop
        self.pool = pool
        self.transport = None
        self.open = False
        self.in_use = True
        self._connection_lost_exc = None
        self.writing_paused = False
        self.writable = asyncio.Event()
        self.ready = asyncio.Event()

    def pause_writing(self):
        super().pause_writing()
        self.writing_paused = True
        self.writable.clear()

    def resume_writing(self):
        super().resume_writing()
        self.writing_paused = False
        self.writable.set()

    def connection_made(self, transport):
        self.transport = transport
        self.open = True
        self.ready.set()

    async def send(self, request):
        # TODO: write request bytes
        #   return HttpResponse
        pass

    def data_received(self, data):
        # TODO: parse response; make like Connection implementation
        print('Data received: {!r}'.format(data.decode()))

        self.data = data
        self.message_ready.set()

    def connection_lost(self, exc):
        self._connection_lost_exc = exc
        self.ready.clear()
        self.open = False
