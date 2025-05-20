try:
    import httptools
except ImportError:
    httptools = None


try:
    import h11
except ImportError:
    h11 = None


if httptools is not None:

    class HTTPToolsResponseParser:
        def __init__(self, connection) -> None:
            self.connection = connection
            self._parser = httptools.HttpResponseParser(connection)

        def feed_data(self, data: bytes) -> None:
            self._parser.feed_data(data)

        def get_status_code(self) -> int:
            return self._parser.get_status_code()

        def reset(self) -> None:
            self._parser = httptools.HttpResponseParser(self.connection)


if h11 is not None:

    class H11ResponseParser:
        def __init__(self, connection) -> None:
            self.connection = connection
            self._conn = h11.Connection(h11.CLIENT)
            self._status_code = None
            self._headers = []
            self._complete = False

        def feed_data(self, data: bytes) -> None:
            self._conn.receive_data(data)
            while True:
                event = self._conn.next_event()
                if event is h11.NEED_DATA:
                    break
                if isinstance(event, h11.Response):
                    self._status_code = event.status_code
                    self._headers = [(k, v) for k, v in event.headers]
                    self.connection.headers = self._headers
                    self.connection.on_headers_complete()
                elif isinstance(event, h11.Data):
                    self.connection.on_body(event.data)
                elif isinstance(event, h11.EndOfMessage):
                    self._complete = True
                    self.connection.on_message_complete()
                # Ignore other events

        def get_status_code(self) -> int:
            return self._status_code or 0

        def reset(self) -> None:
            self._conn = h11.Connection(h11.CLIENT)
            self._status_code = None
            self._headers = []
            self._complete = False


def get_default_parser(client_connection):

    if h11 is not None:
        return H11ResponseParser(client_connection)

    if httptools is not None:
        return HTTPToolsResponseParser(client_connection)

    raise RuntimeError(
        "Missing Python dependencies to provide a default HTTP Response parser. "
        "Install either h11 or httptools."
    )
