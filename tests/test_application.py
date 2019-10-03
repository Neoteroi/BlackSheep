import pytest
import asyncio
import pkg_resources
from typing import List, Optional
from blacksheep.server import Application
from blacksheep import Request, Response, JsonContent, HttpException, TextContent
from blacksheep.server.bindings import FromHeader, FromQuery, FromRoute, FromJson
from tests.utils import ensure_folder


class FakeApplication(Application):

    def __init__(self, *args):
        super().__init__(show_error_details=True, *args)
        self.request = None
        self.response = None

    def setup_controllers(self):
        self.use_controllers()
        self.build_services()
        self.normalize_handlers()

    async def handle(self, request):
        self.request = request
        response = await super().handle(request)
        self.response = response
        return response

    def prepare(self):
        self.normalize_handlers()
        self.configure_middlewares()


def test_application_supports_dynamic_attributes():
    app = FakeApplication()
    foo = object()

    assert hasattr(app, 'foo') is False, 'This test makes sense if such attribute is not defined'
    app.foo = foo
    assert app.foo is foo


def get_example_scope(method: str, path: str, extra_headers=None, query: Optional[bytes] = b''):
    if '?' in path:
        raise ValueError('The path in ASGI messages does not contain query string')
    if query.startswith(b''):
        query = query.lstrip(b'')
    return {
        'type': 'http',
        'http_version': '1.1',
        'server': ['127.0.0.1', 8000],
        'client': ['127.0.0.1', 51492],
        'scheme': 'http',
        'method': method,
        'root_path': '',
        'path': path,
        'raw_path': path.encode(),
        'query_string': query,
        'headers': [
            (b'host', b'127.0.0.1:8000'),
            (b'user-agent', b'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0'),
            (b'accept', b'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
            (b'accept-language', b'en-US,en;q=0.5'),
            (b'accept-encoding', b'gzip, deflate'),
            (b'connection', b'keep-alive'),
            (b'upgrade-insecure-requests', b'1')
        ] + ([tuple(header) for header in extra_headers] if extra_headers else [])
    }


class MockReceive:
    
    def __init__(self, messages=None):
        self.messages = messages or []
        self.index = 0
        
    async def __call__(self):
        try:
            message = self.messages[self.index]
        except IndexError:
            message = b''
        self.index += 1
        await asyncio.sleep(0)
        return {
            'body': message,
            'type': 'http.message',
            'more_body': False if (len(self.messages) == self.index or not message) else True
        }


class MockSend:

    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_application_get_handler():
    app = FakeApplication()

    @app.router.get('/')
    async def home(request):
        pass

    @app.router.get('/foo')
    async def foo(request):
        pass

    send = MockSend()
    receive = MockReceive()

    await app(get_example_scope('GET', '/'), receive, send)

    request = app.request  # type: Request

    assert request is not None

    connection = request.headers[b'connection']
    assert connection == (b'keep-alive',)


@pytest.mark.asyncio
async def test_application_post_multipart_formdata():
    app = FakeApplication()

    @app.router.post(b'/files/upload')
    async def upload_files(request):
        # TODO: add method to test .form() method
        data = await request.multipart()
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
        assert data[2].data == b'Content of a.txt.\r\n'

        assert data[3].name == b'file2'
        assert data[3].file_name == b'a.html'
        assert data[3].content_type == b'text/html'
        assert data[3].data == b'<!DOCTYPE html><title>Content of a.html.</title>\r\n'

        assert data[4].name == b'file3'
        assert data[4].file_name == b'binary'
        assert data[4].content_type == b'application/octet-stream'
        assert data[4].data == 'aωb'.encode('utf8')

        files = await request.files()

        assert files[0].name == b'file1'
        assert files[0].file_name == b'a.txt'
        assert files[0].content_type == b'text/plain'
        assert files[0].data == b'Content of a.txt.\r\n'

        assert files[1].name == b'file2'
        assert files[1].file_name == b'a.html'
        assert files[1].content_type == b'text/html'
        assert files[1].data == b'<!DOCTYPE html><title>Content of a.html.</title>\r\n'

        assert files[2].name == b'file3'
        assert files[2].file_name == b'binary'
        assert files[2].content_type == b'application/octet-stream'
        assert files[2].data == 'aωb'.encode('utf8')

        file_one = await request.files('file1')
        assert file_one[0].name == b'file1'

        return Response(200)

    boundary = b'---------------------0000000000000000000000001'

    content = b'\r\n'.join([
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

    send = MockSend()
    receive = MockReceive([
        content
    ])

    await app(get_example_scope('POST', '/files/upload',
                                [
                                    [b'content-length', str(len(content)).encode()],
                                    [b'content-type', b'multipart/form-data; boundary=' + boundary]
                                ]),
              receive,
              send)

    response = app.response  # type: Response

    data = await response.text()

    assert response is not None
    assert response.status == 200, data


@pytest.mark.asyncio
async def test_application_post_handler():
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

        return Response(201, [(b'Server', b'Python/3.7')], JsonContent({'id': '123'}))

    content = b'{"name":"Celine","kind":"Persian"}'

    send = MockSend()
    receive = MockReceive([content])

    await app(get_example_scope('POST', '/api/cat',
                                [
                                    (b'content-length', str(len(content)).encode())
                                ]),
              receive,
              send)

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

    @app.router.get('/')
    async def example(request):
        nonlocal calls
        calls.append(5)
        return Response(200, [(b'Server', b'Python/3.7')], JsonContent({'id': '123'}))

    app.middlewares.append(middleware_one)
    app.middlewares.append(middleware_two)
    app.configure_middlewares()

    send = MockSend()
    receive = MockReceive([])

    await app(get_example_scope('GET', '/'),
              receive,
              send)

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

    @app.router.get('/')
    async def example(request):
        nonlocal calls
        calls.append(5)
        return Response(200, [(b'Server', b'Python/3.7')], JsonContent({'id': '123'}))

    app.middlewares.append(middleware_one)
    app.middlewares.append(middleware_two)
    app.middlewares.append(middleware_three)
    app.configure_middlewares()

    send = MockSend()
    receive = MockReceive([])

    await app(get_example_scope('GET', '/'),
              receive,
              send)
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

    @app.router.get('/')
    async def example(request):
        nonlocal calls
        calls.append(5)
        return Response(200,
                        [(b'Server', b'Python/3.7')],
                        JsonContent({'id': '123'}))

    app.middlewares.append(middleware_one)
    app.middlewares.append(middleware_two)
    app.middlewares.append(middleware_three)
    app.configure_middlewares()

    send = MockSend()
    receive = MockReceive([])

    await app(get_example_scope('GET', '/'),
              receive,
              send)

    response = app.response  # type: Response
    assert response is not None
    assert response.status == 403
    assert calls == [1, 3, 6, 4, 2]


@pytest.mark.asyncio
async def test_application_post_multipart_formdata_files_handler():
    app = FakeApplication()

    ensure_folder('out')
    ensure_folder('tests/out')

    @app.router.post(b'/files/upload')
    async def upload_files(request):
        files = await request.files('files[]')

        # NB: in this example; we save files to output folder and verify
        # that their binaries are identical
        for part in files:
            full_path = pkg_resources.resource_filename(__name__, 'out/'
                                                        + part.file_name.decode())
            with open(full_path, mode='wb') as saved_file:
                saved_file.write(part.data)

        return Response(200)

    boundary = b'---------------------0000000000000000000000001'
    lines = []

    file_names = {'pexels-photo-126407.jpeg',
                  'pexels-photo-302280.jpeg',
                  'pexels-photo-730896.jpeg'}

    rel_path = 'files/'

    for file_name in file_names:
        full_path = pkg_resources.resource_filename(__name__, rel_path + file_name)
        with open(full_path, mode='rb') as source_file:
            binary = source_file.read()
            lines += [
                boundary,
                b'Content-Disposition: form-data; name="files[]"; filename="' + file_name.encode() + b'"',
                b'',
                binary,
            ]

    lines += [boundary + b'--']
    content = b'\r\n'.join(lines)

    send = MockSend()
    receive = MockReceive([
        content
    ])

    await app(get_example_scope('POST', '/files/upload',
                                [
                                    [b'content-length', str(len(content)).encode()],
                                    [b'content-type', b'multipart/form-data; boundary=' + boundary]
                                ]),
              receive,
              send)

    response = app.response  # type: Response
    body = await response.text()
    assert response.status == 200, body

    # now files are in both folders: compare to ensure they are identical
    for file_name in file_names:
        full_path = pkg_resources.resource_filename(__name__, rel_path + file_name)
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

    @app.router.get('/')
    async def home(request):
        raise HttpException(519)

    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())

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

    @app.router.get('/')
    async def home(request):
        raise HttpException(519)

    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())
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

    @app.router.get('/')
    async def home(request):
        raise CustomException()

    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())

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

    @app.router.get('/')
    async def home(request):
        raise CustomException()

    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())

    response = app.response  # type: Response

    assert response is not None
    text = await response.text()
    assert text == 'Called', 'The response is the one returned by defined http exception handler'


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter,expected_value', [
    ('a', 'a'),
    ('foo', 'foo'),
    ('Hello%20World!!%3B%3B', 'Hello World!!;;'),
])
async def test_handler_route_value_binding_single(parameter, expected_value):
    app = FakeApplication()

    called = False

    @app.router.get('/:value')
    async def home(request, value):
        nonlocal called
        called = True
        assert value == expected_value

    app.normalize_handlers()

    await app(get_example_scope('GET', '/' + parameter), MockReceive(), MockSend())

    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter,expected_a,expected_b', [
    ('a/b', 'a', 'b'),
    ('foo/something', 'foo', 'something'),
    ('Hello%20World!!%3B%3B/another', 'Hello World!!;;', 'another'),
])
async def test_handler_route_value_binding_two(parameter, expected_a, expected_b):
    app = FakeApplication()

    @app.router.get('/:a/:b')
    async def home(request, a, b):
        assert a == expected_a
        assert b == expected_b

    await app(get_example_scope('GET', '/' + parameter), MockReceive(), MockSend())

    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter,expected_value', [
    ('12', 12),
    ('0', 0),
    ('16549', 16549),
])
async def test_handler_route_value_binding_single_int(parameter, expected_value):
    app = FakeApplication()

    called = False

    @app.router.get('/:value')
    async def home(request, value: int):
        nonlocal called
        called = True
        assert value == expected_value

    app.normalize_handlers()

    await app(get_example_scope('GET', '/' + parameter), MockReceive(), MockSend())

    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter', [
    'xx', 'x'
])
async def test_handler_route_value_binding_single_int_invalid(parameter):
    app = FakeApplication()

    called = False

    @app.router.get('/:value')
    async def home(request, value: int):
        nonlocal called
        called = True

    app.normalize_handlers()

    await app(get_example_scope('GET', '/' + parameter), MockReceive(), MockSend())

    assert called is False
    assert app.response.status == 400


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter', [
    'xx', 'x'
])
async def test_handler_route_value_binding_single_float_invalid(parameter):
    app = FakeApplication()

    called = False

    @app.router.get('/:value')
    async def home(request, value: float):
        nonlocal called
        called = True

    app.normalize_handlers()

    await app(get_example_scope('GET', '/' + parameter), MockReceive(), MockSend())

    assert called is False
    assert app.response.status == 400


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter,expected_value', [
    ('12', 12.0),
    ('0', 0.0),
    ('16549.55', 16549.55),
])
async def test_handler_route_value_binding_single_float(parameter, expected_value):
    app = FakeApplication()

    called = False

    @app.router.get('/:value')
    async def home(request, value: float):
        nonlocal called
        called = True
        assert value == expected_value

    app.normalize_handlers()

    await app(get_example_scope('GET', '/' + parameter), MockReceive(), MockSend())

    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter,expected_a,expected_b', [
    ('a/b', 'a', 'b'),
    ('foo/something', 'foo', 'something'),
    ('Hello%20World!!%3B%3B/another', 'Hello World!!;;', 'another'),
])
async def test_handler_route_value_binding_two(parameter, expected_a, expected_b):
    app = FakeApplication()

    @app.router.get('/:a/:b')
    async def home(request, a, b):
        assert a == expected_a
        assert b == expected_b

    app.normalize_handlers()
    await app(get_example_scope('GET', '/' + parameter), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('parameter,expected_a,expected_b,expected_c', [
    ('a/1/12.50', 'a', 1, 12.50),
    ('foo/446/500', 'foo', 446, 500.0),
    ('Hello%20World!!%3B%3B/60/88.05', 'Hello World!!;;', 60, 88.05),
])
async def test_handler_route_value_binding_mixed_types(parameter, expected_a, expected_b, expected_c):
    app = FakeApplication()

    @app.router.get('/:a/:b/:c')
    async def home(request, a: str, b: int, c: float):
        assert a == expected_a
        assert b == expected_b
        assert c == expected_c

    app.normalize_handlers()
    await app(get_example_scope('GET', '/' + parameter), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_value', [
    (b'a=a', ['a']),
    (b'a=foo', ['foo']),
    (b'a=Hello%20World!!%3B%3B', ['Hello World!!;;']),
])
async def test_handler_query_value_binding_single(query, expected_value):
    app = FakeApplication()

    @app.router.get('/')
    async def home(request, a):
        assert a == expected_value

    app.normalize_handlers()

    await app(get_example_scope('GET', '/', query=query), MockReceive(), MockSend())

    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_value', [
    (b'a=10', 10),
    (b'b=20', None),
    (b'', None),
])
async def test_handler_query_value_binding_optional_int(query, expected_value):
    app = FakeApplication()

    @app.router.get('/')
    async def home(request, a: Optional[int]):
        assert a == expected_value

    app.normalize_handlers()
    await app(get_example_scope('GET', '/', query=query), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_value', [
    (b'a=10', 10.0),
    (b'a=12.6', 12.6),
    (b'a=12.6&c=4', 12.6),
    (b'b=20', None),
    (b'', None),
])
async def test_handler_query_value_binding_optional_float(query, expected_value):
    app = FakeApplication()

    @app.router.get('/')
    async def home(request, a: Optional[float]):
        assert a == expected_value

    app.normalize_handlers()
    await app(get_example_scope('GET', '/', query=query), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_value', [
    (b'a=10', [10.0]),
    (b'a=12.6', [12.6]),
    (b'a=12.6&c=4', [12.6]),
    (b'a=12.6&a=4&a=6.6', [12.6, 4.0, 6.6]),
    (b'b=20', None),
    (b'', None),
])
async def test_handler_query_value_binding_optional_list(query, expected_value):
    app = FakeApplication()

    @app.router.get('/')
    async def home(request, a: Optional[List[float]]):
        assert a == expected_value

    app.normalize_handlers()
    await app(get_example_scope('GET', '/', query=query), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_a,expected_b,expected_c', [
    (b'a=a&b=1&c=12.50', 'a', 1, 12.50),
    (b'a=foo&b=446&c=500', 'foo', 446, 500.0),
    (b'a=Hello%20World!!%3B%3B&b=60&c=88.05', 'Hello World!!;;', 60, 88.05),
])
async def test_handler_query_value_binding_mixed_types(query, expected_a, expected_b, expected_c):
    app = FakeApplication()

    @app.router.get('/')
    async def home(request, a: str, b: int, c: float):
        assert a == expected_a
        assert b == expected_b
        assert c == expected_c

    app.normalize_handlers()
    await app(get_example_scope('GET', '/', query=query), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_value', [
    (b'a=Hello%20World!!%3B%3B&a=Hello&a=World', ['Hello World!!;;', 'Hello', 'World']),
])
async def test_handler_query_value_binding_list(query, expected_value):
    app = FakeApplication()

    @app.router.get('/')
    async def home(request, a):
        assert a == expected_value

    app.normalize_handlers()
    await app(get_example_scope('GET', '/', query=query), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_value', [
    (b'a=2', [2]),
    (b'a=2&a=44', [2, 44]),
    (b'a=1&a=5&a=18', [1, 5, 18]),
])
async def test_handler_query_value_binding_list_of_ints(query, expected_value):
    app = FakeApplication()

    @app.router.get('/')
    async def home(request, a: List[int]):
        assert a == expected_value

    app.normalize_handlers()
    await app(get_example_scope('GET', '/', query=query), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_value', [
    (b'a=2', [2.0]),
    (b'a=2.5&a=44.12', [2.5, 44.12]),
    (b'a=1&a=5.55556&a=18.656', [1, 5.55556, 18.656]),
])
async def test_handler_query_value_binding_list_of_floats(query, expected_value):
    app = FakeApplication()

    @app.router.get('/')
    async def home(request, a: List[float]):
        assert a == expected_value

    app.normalize_handlers()
    await app(get_example_scope('GET', '/', query=query), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
async def test_handler_normalize_sync_method():
    app = FakeApplication()

    @app.router.get('/')
    def home(request):
        pass

    app.normalize_handlers()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
async def test_handler_normalize_sync_method_from_header():
    app = FakeApplication()

    @app.router.get('/')
    def home(request, xx: FromHeader(str)):
        assert xx == 'Hello World'

    app.normalize_handlers()
    await app(get_example_scope('GET', '/', [(b'XX', b'Hello World')]), MockReceive(), MockSend())
    text = await app.response.text()
    print(text)
    assert app.response.status == 204


@pytest.mark.asyncio
async def test_handler_normalize_sync_method_from_query():
    app = FakeApplication()

    @app.router.get('/')
    def home(request, xx: FromQuery(int)):
        assert xx == 20

    app.normalize_handlers()
    await app(get_example_scope('GET', '/', query=b'xx=20'), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_values', [
    [b'xx=hello&xx=world&xx=lorem&xx=ipsum', ['hello', 'world', 'lorem', 'ipsum']],
    [b'xx=1&xx=2', ['1', '2']],
    [b'xx=1&yy=2', ['1']]
])
async def test_handler_normalize_sync_method_from_query_default_type(query, expected_values):
    app = FakeApplication()

    @app.router.get('/')
    def home(request, xx: FromQuery()):
        assert xx == expected_values

    app.normalize_handlers()
    await app(get_example_scope('GET', '/', query=query), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
async def test_handler_normalize_method_without_input():
    app = FakeApplication()

    @app.router.get('/')
    async def home():
        pass

    app.normalize_handlers()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('value,expected_value', [
    ['dashboard', 'dashboard'],
    ['hello_world', 'hello_world'],
])
async def test_handler_from_route(value, expected_value):
    app = FakeApplication()

    @app.router.get('/:area')
    async def home(request, area: FromRoute(str)):
        assert area == expected_value

    app.normalize_handlers()
    await app(get_example_scope('GET', '/' + value), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
@pytest.mark.parametrize('value_one,value_two,expected_value_one,expected_value_two', [
    ['en', 'dashboard', 'en', 'dashboard'],
    ['it', 'hello_world', 'it', 'hello_world'],
])
async def test_handler_two_routes_parameters(value_one, value_two, expected_value_one, expected_value_two):
    app = FakeApplication()

    @app.router.get('/:culture_code/:area')
    async def home(request, culture_code: FromRoute(), area: FromRoute()):
        assert culture_code == expected_value_one
        assert area == expected_value_two

    app.normalize_handlers()
    await app(get_example_scope('GET', '/' + value_one + '/' + value_two), MockReceive(), MockSend())
    assert app.response.status == 204


class Item:
    def __init__(self, a, b, c):
        self.a = a
        self.b = b
        self.c = c


@pytest.mark.asyncio
async def test_handler_from_json_parameter():
    app = FakeApplication()

    @app.router.post('/')
    async def home(request, item: FromJson(Item)):
        assert item is not None
        assert item.a == 'Hello'
        assert item.b == 'World'
        assert item.c == 10

    app.normalize_handlers()
    await app(get_example_scope('POST', '/', [
        [b'content-type', b'application/json'],
        [b'content-length', b'32']
    ]), MockReceive([
        b'{"a":"Hello","b":"World","c":10}'
    ]), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
async def test_handler_from_json_parameter_implicit():
    app = FakeApplication()

    @app.router.post('/')
    async def home(request, item: Item):
        assert item is not None
        assert item.a == 'Hello'
        assert item.b == 'World'
        assert item.c == 10

    app.normalize_handlers()
    await app(get_example_scope('POST', '/', [
        [b'content-type', b'application/json'],
        [b'content-length', b'32']
    ]), MockReceive([
        b'{"a":"Hello","b":"World","c":10}'
    ]), MockSend())
    assert app.response.status == 204


@pytest.mark.asyncio
async def test_handler_from_wrong_method_json_parameter_gets_null():
    app = FakeApplication()

    @app.router.get('/')  # <--- NB: wrong http method for posting payloads
    async def home(request, item: FromJson(Item)):
        assert item is None

    app.normalize_handlers()

    await app(get_example_scope('GET', '/', [
        [b'content-type', b'application/json'],
        [b'content-length', b'32']
    ]), MockReceive([
        b'{"a":"Hello","b":"World","c":10}'
    ]), MockSend())

    assert app.response.status == 204
