import pytest
import asyncio
import pkg_resources
from blacksheep.server import Application
from blacksheep.connection import ConnectionHandler
from blacksheep import HttpRequest, HttpResponse, HttpHeader, JsonContent, HttpHeaderCollection
from tests.utils import ensure_folder


class FakeApplication(Application):

    def __init__(self):
        super().__init__()
        self.response_done = asyncio.Event()
        self.request = None
        self.response = None

    async def get_response(self, request):
        response = await super().get_response(request)
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
    handler = ConnectionHandler(app=app, loop=asyncio.get_event_loop())
    handler.connection_made(FakeTransport())
    return handler


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
    request = app.request  # type: HttpRequest

    assert request is not None

    connection = request.headers[b'connection']
    assert connection == [HttpHeader(b'Connection', b'keep-alive')]

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
    request = app.request  # type: HttpRequest

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

        return HttpResponse(200)

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

        return HttpResponse(201, HttpHeaderCollection([HttpHeader(b'Server', b'Python/3.7')]), JsonContent({'id': '123'}))

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
    request = app.request  # type: HttpRequest

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
        return HttpResponse(200, HttpHeaderCollection([HttpHeader(b'Server', b'Python/3.7')]), JsonContent({'id': '123'}))

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
    response = app.response  # type: HttpResponse

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
        return HttpResponse(200, HttpHeaderCollection([HttpHeader(b'Server', b'Python/3.7')]), JsonContent({'id': '123'}))

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
    response = app.response  # type: HttpResponse

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
        return HttpResponse(403)

    @app.router.get(b'/')
    async def example(request):
        nonlocal calls
        calls.append(5)
        return HttpResponse(200,
                            HttpHeaderCollection([HttpHeader(b'Server', b'Python/3.7')]),
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
    response = app.response  # type: HttpResponse
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

        return HttpResponse(200)

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
    response = app.response  # type: HttpResponse
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
