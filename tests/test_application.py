import pytest
import asyncio
import pkg_resources
from typing import List, Optional
from blacksheep.server import Application
from blacksheep.connection import ServerConnection
from blacksheep import Request, Response, Header, JsonContent, Headers, HttpException, TextContent
from tests.utils import ensure_folder


class FakeApplication(Application):

    def __init__(self):
        super().__init__(debug=True)
        self.response_done = asyncio.Event()
        self.request = None
        self.response = None

    async def handle(self, request):
        response = await super().handle(request)
        self.response_done.set()
        self.request = request
        self.response = response
        return response


class FakeTransport:

    def __init__(self):
        self.extra_info = {
            'peername': '127.0.0.1'
        }
        self.reading = True
        self.writing = True
        self.closed = False
        self.bytes = b''

    def pause_reading(self):
        self.reading = False

    def resume_reading(self):
        self.reading = True

    def pause_writing(self):
        self.writing = False

    def resume_writing(self):
        self.writing = True

    def get_extra_info(self, name):
        return self.extra_info.get(name)

    def write(self, data):
        if self.closed:
            raise Exception('Transport is closed')
        self.bytes += data

    def close(self):
        self.closed = True


def get_new_connection_handler(app: Application):
    handler = ServerConnection(app=app, loop=asyncio.get_event_loop())
    handler.connection_made(FakeTransport())
    return handler


def test_application_supports_dynamic_attributes():
    app = Application()
    foo = object()

    assert hasattr(app, 'foo') is False, 'This test makes sense if such attribute is not defined'
    app.foo = foo
    assert app.foo is foo


@pytest.mark.asyncio
async def test_application_get_handler():
    app = FakeApplication()

    @app.router.get(b'/')
    async def home(request):
        pass

    @app.router.get(b'/foo')
    async def foo(request):
        pass

    handler = get_new_connection_handler(app)

    message = b'\r\n'.join([
        b'GET / HTTP/1.1',
        b'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0',
        b'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        b'Accept-Language: en-US,en;q=0.5',
        b'Connection: keep-alive',
        b'Upgrade-Insecure-Requests: 1',
        b'Host: foo\r\n\r\n'
    ])

    handler.data_received(message)

    await app.response_done.wait()
    request = app.request  # type: Request

    assert request is not None

    connection = request.headers[b'connection']
    assert connection == [Header(b'Connection', b'keep-alive')]

    text = await request.text()
    assert text == ''


@pytest.mark.asyncio
async def test_application_post_handler_crlf():
    app = FakeApplication()

    @app.router.post(b'/api/cat')
    async def create_cat(request):
        pass

    handler = get_new_connection_handler(app)

    message = b'\r\n'.join([
        b'POST /api/cat HTTP/1.1',
        b'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0',
        b'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        b'Accept-Language: en-US,en;q=0.5',
        b'Connection: keep-alive',
        b'Upgrade-Insecure-Requests: 1',
        b'Content-Length: 34',
        b'Host: foo\r\n',
        b'{"name":"Celine","kind":"Persian"}\r\n\r\n'
    ])

    handler.data_received(message)
    await app.response_done.wait()
    request = app.request  # type: Request

    assert request is not None

    content = await request.read()
    assert b'{"name":"Celine","kind":"Persian"}' == content


@pytest.mark.asyncio
async def test_application_post_multipart_formdata_handler():
    app = Application(debug=True)

    @app.router.post(b'/files/upload')
    async def upload_files(request):
        data = await request.form()
        assert data is not None

        assert data[0].name == b'text1'
        assert data[0].file_name is None
        assert data[0].content_type is None
        assert data[0].data == b'text default'

        assert data[1].name == b'text2'
        assert data[1].file_name is None
        assert data[1].content_type is None
        assert data[1].data == 'aωb'.encode('utf8')

        assert data[2].name == b'file1'
        assert data[2].file_name == b'a.txt'
        assert data[2].content_type == b'text/plain'
        assert data[2].data == b'Content of a.txt.\n'

        assert data[3].name == b'file2'
        assert data[3].file_name == b'a.html'
        assert data[3].content_type == b'text/html'
        assert data[3].data == b'<!DOCTYPE html><title>Content of a.html.</title>\n'

        assert data[4].name == b'file3'
        assert data[4].file_name == b'binary'
        assert data[4].content_type == b'application/octet-stream'
        assert data[4].data == 'aωb'.encode('utf8')

        files = await request.files()

        assert files[0].name == b'file1'
        assert files[0].file_name == b'a.txt'
        assert files[0].content_type == b'text/plain'
        assert files[0].data == b'Content of a.txt.\n'

        assert files[1].name == b'file2'
        assert files[1].file_name == b'a.html'
        assert files[1].content_type == b'text/html'
        assert files[1].data == b'<!DOCTYPE html><title>Content of a.html.</title>\n'

        assert files[2].name == b'file3'
        assert files[2].file_name == b'binary'
        assert files[2].content_type == b'application/octet-stream'
        assert files[2].data == 'aωb'.encode('utf8')

        file_one = await request.files('file1')
        assert file_one[0].name == b'file1'

        return Response(200)

    handler = get_new_connection_handler(app)

    boundary = b'---------------------0000000000000000000000001'

    content = b'\n'.join([
        boundary,
        b'Content-Disposition: form-data; name="text1"',
        b'',
        b'text default',
        boundary,
        b'Content-Disposition: form-data; name="text2"',
        b'',
        'aωb'.encode('utf8'),
        boundary,
        b'Content-Disposition: form-data; name="file1"; filename="a.txt"',
        b'Content-Type: text/plain',
        b'',
        b'Content of a.txt.',
        b'',
        boundary,
        b'Content-Disposition: form-data; name="file2"; filename="a.html"',
        b'Content-Type: text/html',
        b'',
        b'<!DOCTYPE html><title>Content of a.html.</title>',
        b'',
        boundary,
        b'Content-Disposition: form-data; name="file3"; filename="binary"',
        b'Content-Type: application/octet-stream',
        b'',
        'aωb'.encode('utf8'),
        boundary + b'--'
    ])

    message = b'\n'.join([
        b'POST /files/upload HTTP/1.1',
        b'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0',
        b'Content-Type: multipart/form-data; boundary=' + boundary,
        b'Content-Length: ' + str(len(content)).encode(),
        b'Host: foo\n',
        content,
        b'\r\n\r\n'
    ])

    handler.data_received(message)


@pytest.mark.asyncio
async def test_application_post_handler_lf():
    app = FakeApplication()

    called_times = 0

    @app.router.post(b'/api/cat')
    async def create_cat(request):
        nonlocal called_times
        called_times += 1
        assert request is not None

        content = await request.read()
        assert b'{"name":"Celine","kind":"Persian"}' == content

        data = await request.json()
        assert {"name": "Celine", "kind": "Persian"} == data

        return Response(201, Headers([Header(b'Server', b'Python/3.7')]), JsonContent({'id': '123'}))

    handler = get_new_connection_handler(app)

    message = b'\n'.join([
        b'POST /api/cat HTTP/1.1',
        b'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0',
        b'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        b'Accept-Language: en-US,en;q=0.5',
        b'Connection: keep-alive',
        b'Upgrade-Insecure-Requests: 1',
        b'Content-Length: 34',
        b'Host: foo\n',
        b'{"name":"Celine","kind":"Persian"}\n\n'
    ])

    handler.data_received(message)

    await app.response_done.wait()
    request = app.request  # type: Request

    assert request is not None

    content = await request.read()
    assert b'{"name":"Celine","kind":"Persian"}' == content

    data = await request.json()
    assert {"name": "Celine", "kind": "Persian"} == data

    response = app.response
    assert called_times == 1
    response_data = await response.json()
    assert {'id': '123'} == response_data


@pytest.mark.asyncio
async def test_application_middlewares_two():
    app = FakeApplication()

    calls = []

    async def middleware_one(request, handler):
        nonlocal calls
        calls.append(1)
        response = await handler(request)
        calls.append(2)
        return response

    async def middleware_two(request, handler):
        nonlocal calls
        calls.append(3)
        response = await handler(request)
        calls.append(4)
        return response

    @app.router.get(b'/')
    async def example(request):
        nonlocal calls
        calls.append(5)
        return Response(200, Headers([Header(b'Server', b'Python/3.7')]), JsonContent({'id': '123'}))

    app.middlewares.append(middleware_one)
    app.middlewares.append(middleware_two)
    app.configure_middlewares()

    handler = get_new_connection_handler(app)

    message = b'\n'.join([
        b'GET / HTTP/1.1',
        b'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0',
        b'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        b'Accept-Language: en-US,en;q=0.5',
        b'Connection: keep-alive',
        b'Host: foo\n',
        b'\n\n'
    ])

    handler.data_received(message)

    assert handler.transport.closed is False
    await app.response_done.wait()
    response = app.response  # type: Response

    assert response is not None
    assert response.status == 200
    assert calls == [1, 3, 5, 4, 2]


@pytest.mark.asyncio
async def test_application_middlewares_three():
    app = FakeApplication()

    calls = []

    async def middleware_one(request, handler):
        nonlocal calls
        calls.append(1)
        response = await handler(request)
        calls.append(2)
        return response

    async def middleware_two(request, handler):
        nonlocal calls
        calls.append(3)
        response = await handler(request)
        calls.append(4)
        return response

    async def middleware_three(request, handler):
        nonlocal calls
        calls.append(6)
        response = await handler(request)
        calls.append(7)
        return response

    @app.router.get(b'/')
    async def example(request):
        nonlocal calls
        calls.append(5)
        return Response(200, Headers([Header(b'Server', b'Python/3.7')]), JsonContent({'id': '123'}))

    app.middlewares.append(middleware_one)
    app.middlewares.append(middleware_two)
    app.middlewares.append(middleware_three)
    app.configure_middlewares()

    handler = get_new_connection_handler(app)

    message = b'\n'.join([
        b'GET / HTTP/1.1',
        b'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0',
        b'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        b'Accept-Language: en-US,en;q=0.5',
        b'Connection: keep-alive',
        b'Host: foo\n',
        b'\n\n'
    ])

    handler.data_received(message)
    await app.response_done.wait()
    response = app.response  # type: Response

    assert response is not None
    assert response.status == 200
    assert calls == [1, 3, 6, 5, 7, 4, 2]


@pytest.mark.asyncio
async def test_application_middlewares_skip_handler():
    app = FakeApplication()

    calls = []

    async def middleware_one(request, handler):
        nonlocal calls
        calls.append(1)
        response = await handler(request)
        calls.append(2)
        return response

    async def middleware_two(request, handler):
        nonlocal calls
        calls.append(3)
        response = await handler(request)
        calls.append(4)
        return response

    async def middleware_three(request, handler):
        nonlocal calls
        calls.append(6)
        return Response(403)

    @app.router.get(b'/')
    async def example(request):
        nonlocal calls
        calls.append(5)
        return Response(200,
                            Headers([Header(b'Server', b'Python/3.7')]),
                            JsonContent({'id': '123'}))

    app.middlewares.append(middleware_one)
    app.middlewares.append(middleware_two)
    app.middlewares.append(middleware_three)
    app.configure_middlewares()

    handler = get_new_connection_handler(app)

    message = b'\n'.join([
        b'GET / HTTP/1.1',
        b'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0',
        b'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        b'Accept-Language: en-US,en;q=0.5',
        b'Connection: keep-alive',
        b'Host: foo\n',
        b'\n\n'
    ])

    handler.data_received(message)
    assert handler.transport.closed is False
    await app.response_done.wait()
    response = app.response  # type: Response
    assert response is not None
    assert response.status == 403
    assert calls == [1, 3, 6, 4, 2]


@pytest.mark.asyncio
async def test_application_post_multipart_formdata_files_handler():
    app = FakeApplication()

    ensure_folder('out')

    @app.router.post(b'/files/upload')
    async def upload_files(request):
        files = await request.files('files[]')

        # NB: in this example; we save files to output folder and verify
        # that their binaries are identical
        for part in files:
            full_path = pkg_resources.resource_filename(__name__, './out/'
                                                        + part.file_name.decode())
            with open(full_path, mode='wb') as saved_file:
                saved_file.write(part.data)

        return Response(200)

    handler = get_new_connection_handler(app)
    boundary = b'---------------------0000000000000000000000001'
    lines = []

    file_names = {'pexels-photo-126407.jpeg',
                  'pexels-photo-302280.jpeg',
                  'pexels-photo-730896.jpeg'}

    for file_name in file_names:
        full_path = pkg_resources.resource_filename(__name__, './files/' + file_name)
        with open(full_path, mode='rb') as source_file:
            binary = source_file.read()
            lines += [
                boundary,
                b'Content-Disposition: form-data; name="files[]"; filename="' + file_name.encode() + b'"',
                b'',
                binary,
            ]

    lines += [boundary + b'--']
    content = b'\n'.join(lines)

    message = b'\n'.join([
        b'POST /files/upload HTTP/1.1',
        b'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0',
        b'Content-Type: multipart/form-data; boundary=' + boundary,
        b'Content-Length: ' + str(len(content)).encode(),
        b'Host: foo\n',
        content,
        b'\r\n\r\n'
    ])

    handler.data_received(message)

    await app.response_done.wait()
    response = app.response  # type: Response
    assert response.status == 200

    # now files are in both folders: compare to ensure they are identical
    for file_name in file_names:
        full_path = pkg_resources.resource_filename(__name__, './files/' + file_name)
        copy_full_path = pkg_resources.resource_filename(__name__, './out/' + file_name)

        with open(full_path, mode='rb') as source_file:
            binary = source_file.read()
            with open(copy_full_path, mode='rb') as file_clone:
                clone_binary = file_clone.read()

                assert binary == clone_binary


@pytest.mark.asyncio
async def test_application_http_exception_handlers():
    app = FakeApplication()

    called = False

    async def exception_handler(self, request, http_exception):
        nonlocal called
        assert request is not None
        called = True
        return Response(200, content=TextContent('Called'))

    app.exceptions_handlers[519] = exception_handler

    @app.router.get(b'/')
    async def home(request):
        raise HttpException(519)

    handler = get_new_connection_handler(app)

    message = b'\r\n'.join([
        b'GET / HTTP/1.1',
        b'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0',
        b'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        b'Accept-Language: en-US,en;q=0.5',
        b'Connection: keep-alive',
        b'Upgrade-Insecure-Requests: 1',
        b'Host: foo\r\n\r\n'
    ])

    handler.data_received(message)

    await app.response_done.wait()
    response = app.response  # type: Response

    assert response is not None
    assert called is True, 'Http exception handler was called'

    text = await response.text()
    assert text == 'Called', 'The response is the one returned by defined http exception handler'


@pytest.mark.asyncio
async def test_application_http_exception_handlers_called_in_application_context():
    app = FakeApplication()

    async def exception_handler(self, request, http_exception):
        nonlocal app
        assert self is app
        return Response(200, content=TextContent('Called'))

    app.exceptions_handlers[519] = exception_handler

    @app.router.get(b'/')
    async def home(request):
        raise HttpException(519)

    handler = get_new_connection_handler(app)

    message = b'\r\n'.join([
        b'GET / HTTP/1.1',
        b'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0',
        b'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        b'Accept-Language: en-US,en;q=0.5',
        b'Connection: keep-alive',
        b'Upgrade-Insecure-Requests: 1',
        b'Host: foo\r\n\r\n'
    ])

    handler.data_received(message)

    await app.response_done.wait()
    response = app.response  # type: Response

    assert response is not None
    text = await response.text()
    assert text == 'Called', 'The response is the one returned by defined http exception handler'


@pytest.mark.asyncio
async def test_application_user_defined_exception_handlers():
    app = FakeApplication()

    called = False

    class CustomException(Exception):
        pass

    async def exception_handler(self, request, exception: CustomException):
        nonlocal called
        assert request is not None
        called = True
        return Response(200, content=TextContent('Called'))

    app.exceptions_handlers[CustomException] = exception_handler

    @app.router.get(b'/')
    async def home(request):
        raise CustomException()

    handler = get_new_connection_handler(app)

    message = b'\r\n'.join([
        b'GET / HTTP/1.1',
        b'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0',
        b'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        b'Accept-Language: en-US,en;q=0.5',
        b'Connection: keep-alive',
        b'Upgrade-Insecure-Requests: 1',
        b'Host: foo\r\n\r\n'
    ])

    handler.data_received(message)

    await app.response_done.wait()
    response = app.response  # type: Response

    assert response is not None
    assert called is True, 'Http exception handler was called'

    text = await response.text()
    assert text == 'Called', 'The response is the one returned by defined http exception handler'


@pytest.mark.asyncio
async def test_application_user_defined_exception_handlers_called_in_application_context():
    app = FakeApplication()

    class CustomException(Exception):
        pass

    async def exception_handler(self, request, exc: CustomException):
        nonlocal app
        assert self is app
        assert isinstance(exc, CustomException)
        return Response(200, content=TextContent('Called'))

    app.exceptions_handlers[CustomException] = exception_handler

    @app.router.get(b'/')
    async def home(request):
        raise CustomException()

    handler = get_new_connection_handler(app)

    message = b'\r\n'.join([
        b'GET / HTTP/1.1',
        b'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0',
        b'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        b'Accept-Language: en-US,en;q=0.5',
        b'Connection: keep-alive',
        b'Upgrade-Insecure-Requests: 1',
        b'Host: foo\r\n\r\n'
    ])

    handler.data_received(message)

    await app.response_done.wait()
    response = app.response  # type: Response

    assert response is not None
    text = await response.text()
    assert text == 'Called', 'The response is the one returned by defined http exception handler'


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter,expected_value', [
    (b'a', 'a'),
    (b'foo', 'foo'),
    (b'Hello%20World!!%3B%3B', 'Hello World!!;;'),
])
async def test_handler_route_value_binding_single(parameter, expected_value):
    app = FakeApplication()

    called = False

    @app.router.get(b'/:value')
    async def home(request, value):
        nonlocal called
        called = True
        assert value == expected_value

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + parameter + b' HTTP/1.1\r\nHost: foo\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter,expected_a,expected_b', [
    (b'a/b', 'a', 'b'),
    (b'foo/something', 'foo', 'something'),
    (b'Hello%20World!!%3B%3B/another', 'Hello World!!;;', 'another'),
])
async def test_handler_route_value_binding_two(parameter, expected_a, expected_b):
    app = FakeApplication()

    called = False

    @app.router.get(b'/:a/:b')
    async def home(request, a, b):
        nonlocal called
        called = True
        assert a == expected_a
        assert b == expected_b

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + parameter + b' HTTP/1.1\r\nHost: foo\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter,expected_value', [
    (b'12', 12),
    (b'0', 0),
    (b'16549', 16549),
])
async def test_handler_route_value_binding_single_int(parameter, expected_value):
    app = FakeApplication()

    called = False

    @app.router.get(b'/:value')
    async def home(request, value: int):
        nonlocal called
        called = True
        assert value == expected_value

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + parameter + b' HTTP/1.1\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter', [
    b'xx', b'x'
])
async def test_handler_route_value_binding_single_int_invalid(parameter):
    app = FakeApplication()

    called = False

    @app.router.get(b'/:value')
    async def home(request, value: int):
        nonlocal called
        called = True

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + parameter + b' HTTP/1.1\r\n\r\n')

    await app.response_done.wait()
    assert called is False
    assert app.response.status == 400


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter', [
    b'xx', b'x'
])
async def test_handler_route_value_binding_single_float_invalid(parameter):
    app = FakeApplication()

    called = False

    @app.router.get(b'/:value')
    async def home(request, value: float):
        nonlocal called
        called = True

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + parameter + b' HTTP/1.1\r\n\r\n')

    await app.response_done.wait()
    assert called is False
    assert app.response.status == 400


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter,expected_value', [
    (b'12', 12.0),
    (b'0', 0.0),
    (b'16549.55', 16549.55),
])
async def test_handler_route_value_binding_single_float(parameter, expected_value):
    app = FakeApplication()

    called = False

    @app.router.get(b'/:value')
    async def home(request, value: float):
        nonlocal called
        called = True
        assert value == expected_value

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + parameter + b' HTTP/1.1\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter,expected_a,expected_b', [
    (b'a/b', 'a', 'b'),
    (b'foo/something', 'foo', 'something'),
    (b'Hello%20World!!%3B%3B/another', 'Hello World!!;;', 'another'),
])
async def test_handler_route_value_binding_two(parameter, expected_a, expected_b):
    app = FakeApplication()

    called = False

    @app.router.get(b'/:a/:b')
    async def home(request, a, b):
        nonlocal called
        called = True
        assert a == expected_a
        assert b == expected_b

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + parameter + b' HTTP/1.1\r\nHost: foo\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter,expected_a,expected_b,expected_c', [
    (b'a/1/12.50', 'a', 1, 12.50),
    (b'foo/446/500', 'foo', 446, 500.0),
    (b'Hello%20World!!%3B%3B/60/88.05', 'Hello World!!;;', 60, 80.05),
])
async def test_handler_route_value_binding_mixed_types(parameter, expected_a, expected_b, expected_c):
    app = FakeApplication()

    called = False

    @app.router.get(b'/:a/:b/:c')
    async def home(request, a: str, b: int, c: float):
        nonlocal called
        called = True
        assert a == expected_a
        assert b == expected_b
        assert c == expected_c

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + parameter + b' HTTP/1.1\r\nHost: foo\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_value', [
    (b'?a=a', 'a'),
    (b'?a=foo', 'foo'),
    (b'?a=Hello%20World!!%3B%3B', 'Hello World!!;;'),
])
async def test_handler_query_value_binding_single(query, expected_value):
    app = FakeApplication()

    called = False

    @app.router.get(b'/')
    async def home(request, value):
        nonlocal called
        called = True
        assert value == expected_value

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + query + b' HTTP/1.1\r\nHost: foo\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_value', [
    (b'?a=10', 10),
    (b'?b=20', None),
    (b'', None),
])
async def test_handler_query_value_binding_optional_int(query, expected_value):
    app = FakeApplication()

    called = False

    @app.router.get(b'/')
    async def home(request, a: Optional[int]):
        nonlocal called
        called = True
        assert a == expected_value

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + query + b' HTTP/1.1\r\nHost: foo\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_value', [
    (b'?a=10', 10.0),
    (b'?a=12.6', 12.6),
    (b'?a=12.6&c=4', 12.6),
    (b'?b=20', None),
    (b'', None),
])
async def test_handler_query_value_binding_optional_float(query, expected_value):
    app = FakeApplication()

    called = False

    @app.router.get(b'/')
    async def home(request, a: Optional[float]):
        nonlocal called
        called = True
        assert a == expected_value

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + query + b' HTTP/1.1\r\nHost: foo\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_value', [
    (b'?a=10', [10.0]),
    (b'?a=12.6', [12.6]),
    (b'?a=12.6&c=4', [12.6]),
    (b'?a=12.6&a=4&a=6.6', [12.6, 4.0, 6.6]),
    (b'?b=20', None),
    (b'', None),
])
async def test_handler_query_value_binding_optional_list(query, expected_value):
    app = FakeApplication()

    called = False

    @app.router.get(b'/')
    async def home(request, a: Optional[List[float]]):
        nonlocal called
        called = True
        assert a == expected_value

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + query + b' HTTP/1.1\r\nHost: foo\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_a,expected_b,expected_c', [
    (b'?a=a&b=1&c=12.50', 'a', 1, 12.50),
    (b'?a=foo&b=446&c=500', 'foo', 446, 500.0),
    (b'?a=Hello%20World!!%3B%3B&b=60&c=88.05', 'Hello World!!;;', 60, 80.05),
])
async def test_handler_query_value_binding_mixed_types(query, expected_a, expected_b, expected_c):
    app = FakeApplication()

    called = False

    @app.router.get(b'/')
    async def home(request, a: str, b: int, c: float):
        nonlocal called
        called = True
        assert a == expected_a
        assert b == expected_b
        assert c == expected_c

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + query + b' HTTP/1.1\r\nHost: foo\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_value', [
    (b'?a=Hello%20World!!%3B%3B&a=Hello&a=World', ['Hello World!!;;', 'Hello', 'World']),
])
async def test_handler_query_value_binding_list(query, expected_value):
    app = FakeApplication()

    called = False

    @app.router.get(b'/')
    async def home(request, value):
        nonlocal called
        called = True
        assert value == expected_value

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + query + b' HTTP/1.1\r\nHost: foo\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_value', [
    (b'?a=2', [2]),
    (b'?a=2&a=44', [2, 44]),
    (b'?a=1&a=5&a=18', [1, 5, 18]),
])
async def test_handler_query_value_binding_list_of_ints(query, expected_value):
    app = FakeApplication()

    called = False

    @app.router.get(b'/')
    async def home(request, a: List[int]):
        nonlocal called
        called = True
        assert a == expected_value

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + query + b' HTTP/1.1\r\nHost: foo\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_value', [
    (b'?a=2', [2.0]),
    (b'?a=2.5&a=44.12', [2.5, 44.12]),
    (b'?a=1&a=5.55556&a=18.656', [1, 5.55556, 18.656]),
])
async def test_handler_query_value_binding_list_of_floats(query, expected_value):
    app = FakeApplication()

    called = False

    @app.router.get(b'/')
    async def home(request, a: List[float]):
        nonlocal called
        called = True
        assert a == expected_value

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET /' + query + b' HTTP/1.1\r\nHost: foo\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
async def test_handler_normalize_sync_method():
    app = FakeApplication()

    called = False

    @app.router.get(b'/')
    def home(request):
        nonlocal called
        called = True

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET / HTTP/1.1\r\nHost: foo\r\n\r\n')

    await app.response_done.wait()
    assert called is True


@pytest.mark.asyncio
async def test_handler_normalize_method_without_input():
    app = FakeApplication()

    called = False

    @app.router.get(b'/')
    async def home():
        nonlocal called
        called = True

    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET / HTTP/1.1\r\nHost: foo\r\n\r\n')

    await app.response_done.wait()
    assert called is True
