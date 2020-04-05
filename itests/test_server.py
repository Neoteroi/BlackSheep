import json
import os
import shutil
from base64 import urlsafe_b64encode
from urllib.parse import unquote
from uuid import uuid4

import pytest

from .lorem import LOREM_IPSUM
from .client_fixtures import get_static_path
from .server_fixtures import *  # NoQA
from .utils import assert_files_equals, ensure_success


def test_hello_world(session):
    response = session.get('/hello-world')
    ensure_success(response)
    assert response.text == 'Hello, World!'


def test_not_found(session):
    response = session.get('/not-found')
    assert response.status_code == 404


@pytest.mark.parametrize('query,echoed', [
    ('?foo=120&name=Foo&age=20', {
        'foo': ['120'],
        'name': ['Foo'],
        'age': ['20']
    }),
    ('?foo=120&foo=66&foo=124', {
        'foo': ['120', '66', '124']
    }),
    ('?foo=120&foo=66&foo=124&x=Hello%20World!!%20%3F', {
        'foo': ['120', '66', '124'],
        'x': ['Hello World!! ?']
    })
])
def test_query(session, query, echoed):
    response = session.get('/echo-query' + query)
    ensure_success(response)

    content = response.json()
    assert content == echoed


@pytest.mark.parametrize('fragment,echoed', [
    ('Hello/World/777', {
        'one': 'Hello',
        'two': 'World',
        'three': '777'
    }),
    ('Hello%20World!!%20%3F/items/archived', {
        'one': 'Hello World!! ?',
        'two': 'items',
        'three': 'archived'
    }),
])
def test_route(session, fragment, echoed):
    response = session.get('/echo-route/' + fragment)
    ensure_success(response)

    content = response.json()
    assert content == echoed


@pytest.mark.parametrize('fragment,echoed', [
    ('Hello/World/777', {
        'one': 'Hello',
        'two': 'World',
        'three': '777'
    }),
    ('Hello%20World!!%20%3F/items/archived', {
        'one': 'Hello World!! ?',
        'two': 'items',
        'three': 'archived'
    }),
])
def test_query_autobind(session, fragment, echoed):
    response = session.get('/echo-route-autobind/' + fragment)
    ensure_success(response)

    content = response.json()
    assert content == echoed


@pytest.mark.parametrize('headers', [
    {'x-foo': str(uuid4())},
    {'x-a': 'Hello', 'x-b': 'World', 'x-c': '!!'}
])
def test_headers(session, headers):
    response = session.head('/echo-headers', headers=headers)
    ensure_success(response)

    for key, value in headers.items():
        header = response.headers[key]
        assert value == header


@pytest.mark.parametrize('cookies', [
    {'x-foo': str(uuid4())},
    {'x-a': 'Hello', 'x-b': 'World', 'x-c': '!!'}
])
def test_cookies(session, cookies):
    response = session.get('/echo-cookies', cookies=cookies)
    ensure_success(response)

    data = response.json()

    for key, value in cookies.items():
        header = data[key]
        assert value == header


@pytest.mark.parametrize('name,value', [
    ('Foo', 'Foo'),
    ('Character-Name', 'Charlie Brown')
])
def test_set_cookie(session, name, value):
    response = session.get('/set-cookie', params=dict(name=name, value=value))
    ensure_success(response)

    assert value == unquote(response.cookies[name])


@pytest.mark.parametrize('data', [
    {
        'name': 'Gorun Nova',
        'type': 'Sword'
    },
    {
        'id': str(uuid4()),
        'price': 15.15,
        'name': 'Ravenclaw T-Shirt'
    },
])
def test_post_json(session, data):
    response = session.post('/echo-posted-json', json=data)
    ensure_success(response)

    assert response.json() == data


@pytest.mark.parametrize('data', [
    {
        'name': 'Gorun Nova',
        'power': 9000
    },
    {
        'name': 'Hello World',
        'power': 15.80
    },
])
def test_post_json_autobind(session, data):
    response = session.post('/echo-posted-json-autobind', json=data)
    ensure_success(response)

    assert response.json() == data


@pytest.mark.parametrize('data,echoed', [
    ({
        'name': 'Gorun Nova',
        'type': 'Sword'
     },
     {
         'name': 'Gorun Nova',
         'type': 'Sword'
     }),
    ({
        'id': 123,
        'price': 15.15,
        'name': 'Ravenclaw T-Shirt'
    },
     {
         'id': '123',
         'price': '15.15',
         'name': 'Ravenclaw T-Shirt'
     })
])
def test_post_form_urlencoded(session, data, echoed):
    response = session.post('/echo-posted-form', data=data)
    ensure_success(response)

    content = response.json()
    assert content == echoed


def test_post_multipart_form_with_files(session):

    if os.path.exists('out'):
        shutil.rmtree('out')

    response = session.post('/upload-files', files=[
        ('images', ('one.jpg',
                    open(get_static_path('pexels-photo-126407.jpeg'), 'rb'),
                    'image/jpeg')),
        ('images', ('two.jpg',
                    open(get_static_path('pexels-photo-923360.jpeg'), 'rb'),
                    'image/jpeg'))
    ])
    ensure_success(response)

    assert_files_equals(f'./out/one.jpg',
                        get_static_path('pexels-photo-126407.jpeg'))
    assert_files_equals(f'./out/two.jpg',
                        get_static_path('pexels-photo-923360.jpeg'))


def test_exception_handling_with_details(session):
    response = session.get('/crash')

    assert response.status_code == 500
    details = response.text
    assert 'itests/app.py' in details
    assert 'itests.utils.CrashTest: Crash Test!' in details


def test_exception_handling_without_details(session_two):
    # By default, the server must hide error details
    response = session_two.get('/crash')

    assert response.status_code == 500
    assert response.text == 'Internal server error.'


def test_exception_handling_with_response(session_two):
    # By default, the server must hide error details
    response = session_two.get('/handled-crash')

    assert response.status_code == 200
    assert response.text == 'Fake exception, to test handlers'


if os.environ.get('SLOW_TESTS') == '1':

    def test_low_level_hello_world(socket_connection, server_host):

        lines = b'\r\n'.join([
            b'GET /hello-world HTTP/1.1',
            b'Host: ' + server_host.encode(),
            b'\r\n\r\n'
        ])

        socket_connection.send(lines)

        response_bytes = bytearray()

        while True:
            chunk = socket_connection.recv(1024)

            if chunk:
                response_bytes.extend(chunk)
            else:
                break

        value = bytes(response_bytes)
        assert b'content-length: 13' in value
        assert value.endswith(b'Hello, World!')

    @pytest.mark.parametrize('value', [
        LOREM_IPSUM
    ])
    def test_posting_chunked_text(socket_connection, server_host, value):

        lines = b'\r\n'.join([
            b'POST /echo-chunked-text HTTP/1.1',
            b'Host: ' + server_host.encode(),
            b'Transfer-Encoding: chunked',
            b'Content-Type: text/plain; charset=utf-8'
        ])

        socket_connection.send(lines)

        for line in value.splitlines():
            chunk = line.encode('utf-8')
            socket_connection.send((hex(len(chunk))).encode()[2:] + b'\r\n' + chunk + b'\r\n')

        socket_connection.send(b'0\r\n\r\n')

        response_bytes = bytearray()

        while True:
            chunk = socket_connection.recv(1024)

            if chunk:
                response_bytes.extend(chunk)
            else:
                break

        response_bytes = bytes(response_bytes)
        value = value.replace('\n', '')  # NB: splitlines removes line breaks

        content_length_header = b'content-length: ' + str(len(value)).encode()

        assert content_length_header in response_bytes
        assert response_bytes.endswith(value.encode('utf-8'))

    @pytest.mark.parametrize('value', [
        LOREM_IPSUM
    ])
    def test_posting_chunked_text_streamed(socket_connection, server_host, value):

        lines = b'\r\n'.join([
            b'POST /echo-streamed-text HTTP/1.1',
            b'Host: ' + server_host.encode(),
            b'Transfer-Encoding: chunked',
            b'Content-Type: text/plain; charset=utf-8'
        ])

        socket_connection.send(lines)

        for line in value.splitlines():
            chunk = line.encode('utf-8')
            socket_connection.send((hex(len(chunk))).encode()[2:] + b'\r\n' + chunk + b'\r\n')

        socket_connection.send(b'0\r\n\r\n')

        response_bytes = bytearray()

        while True:
            chunk = socket_connection.recv(1024)

            if chunk:
                response_bytes.extend(chunk)
            else:
                break

        response_bytes = bytes(response_bytes)
        # value = value.replace('\n', '')  # NB: splitlines removes line breaks

        assert b'transfer-encoding: chunked' in response_bytes


@pytest.mark.parametrize('url_path,file_name', [
    ('/pexels-photo-923360.jpeg', 'example.jpg'),
    ('/example.html', 'example.html')
])
def test_get_file(session, url_path, file_name):
    response = session.get(url_path, stream=True)
    ensure_success(response)

    with open(file_name, 'wb') as output_file:
        for chunk in response:
            output_file.write(chunk)

    assert_files_equals(get_static_path(url_path), file_name)


def test_get_file_response_with_path(session):
    response = session.get('/file-response-with-path', stream=True)
    ensure_success(response)

    with open('nice-cat.jpg', 'wb') as output_file:
        for chunk in response:
            output_file.write(chunk)

    assert_files_equals(get_static_path('pexels-photo-923360.jpeg'),
                        'nice-cat.jpg')


def test_get_file_response_with_generator(session):
    response = session.get('/file-response-with-generator', stream=True)
    ensure_success(response)

    body = bytearray()
    for chunk in response:
        body.extend(chunk)

    text = body.decode('utf8')

    assert text == """Black Knight: None shall pass.
King Arthur: What?
Black Knight: None shall pass.
King Arthur: I have no quarrel with you, good Sir Knight, but I must cross this bridge.
Black Knight: Then you shall die.
King Arthur: I command you, as King of the Britons, to stand aside!
Black Knight: I move for no man.
King Arthur: So be it!
[rounds of melee, with Arthur cutting off the left arm of the black knight.]
King Arthur: Now stand aside, worthy adversary.
Black Knight: Tis but a scratch.
"""


def test_get_file_with_bytes(session):
    response = session.get('/file-response-with-bytes')
    ensure_success(response)

    text = response.text

    assert text == """Black Knight: None shall pass.
King Arthur: What?
Black Knight: None shall pass.
King Arthur: I have no quarrel with you, good Sir Knight, but I must cross this bridge.
Black Knight: Then you shall die.
King Arthur: I command you, as King of the Britons, to stand aside!
Black Knight: I move for no man.
King Arthur: So be it!
[rounds of melee, with Arthur cutting off the left arm of the black knight.]
King Arthur: Now stand aside, worthy adversary.
Black Knight: Tis but a scratch.
"""


def test_get_file_with_bytesio(session):
    response = session.get('/file-response-with-bytesio')
    ensure_success(response)

    text = response.text

    assert text == """some initial binary data: """


def test_xml_files_are_not_served(session):
    response = session.get('/example.xml', stream=True)

    assert response.status_code == 404


@pytest.mark.parametrize('claims,expected_status', [
    (None, 401),
    ({
         'id': '001',
         'name': 'Charlie Brown'
     }, 204),
])
def test_requires_authenticated_user(session_two, claims, expected_status):
    headers = {
        'Authorization': urlsafe_b64encode(json.dumps(claims).encode('utf8')).decode()
    } if claims else {}
    response = session_two.get('/only-for-authenticated-users', headers=headers)

    assert response.status_code == expected_status


@pytest.mark.parametrize('claims,expected_status', [
    (None, 401),
    ({
        'id': '001',
        'name': 'Charlie Brown',
        'role': 'user'
     }, 401),
    ({
        'id': '002',
        'name': 'Snoopy',
        'role': 'admin'  # according to rules coded in app_two.py
     }, 204),
])
def test_requires_admin_user(session_two, claims, expected_status):
    headers = {
        'Authorization': urlsafe_b64encode(json.dumps(claims).encode('utf8')).decode()
    } if claims else {}
    response = session_two.get('/only-for-admins', headers=headers)

    assert response.status_code == expected_status
