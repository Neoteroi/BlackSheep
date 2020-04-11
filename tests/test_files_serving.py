import pkg_resources
import pytest

from blacksheep import Request
from blacksheep.common.files.asyncfs import FilesHandler
from blacksheep.server.files import FileInfo, RangeNotSatisfiable
from blacksheep.server.files.dynamic import get_response_for_file


def _get_file_path(file_name):
    return pkg_resources.resource_filename(__name__, './files/' + file_name)


@pytest.mark.asyncio
async def test_get_response_for_file_raise_for_file_not_found():
    with pytest.raises(FileNotFoundError):
        get_response_for_file(FilesHandler(),
                              Request('GET', b'/example.txt', None),
                              'example.txt',
                              1200)


TEST_FILES = [
    _get_file_path('lorem-ipsum.txt'),
    _get_file_path('example.txt'),
    _get_file_path('pexels-photo-126407.jpeg')
]
TEST_FILES_METHODS = [[i, 'GET'] for i in TEST_FILES] + [[i, 'HEAD']
                                                         for i in TEST_FILES]


@pytest.mark.asyncio
@pytest.mark.parametrize('file_path', TEST_FILES)
async def test_get_response_for_file_returns_file_contents(file_path):
    response = get_response_for_file(FilesHandler(),
                                     Request('GET', b'/example', None),
                                     file_path,
                                     1200)

    assert response.status == 200
    data = await response.read()

    with open(file_path, mode='rb') as test_file:
        contents = test_file.read()

    assert data == contents


@pytest.mark.asyncio
@pytest.mark.parametrize('file_path,method', TEST_FILES_METHODS)
async def test_get_response_for_file_returns_headers(file_path, method):
    response = get_response_for_file(FilesHandler(),
                                     Request(method, b'/example', None),
                                     file_path,
                                     1200)

    assert response.status == 200

    info = FileInfo.from_path(file_path)
    expected_headers = {
        b'etag': info.etag.encode(),
        b'last-modified': str(info.modified_time).encode(),
        b'accept-ranges': b'bytes',
        b'cache-control': b'max-age=1200'
    }

    for expected_header_name, expected_header_value in expected_headers.items():
        value = response.get_single_header(expected_header_name)

        assert value is not None
        assert value == expected_header_value


@pytest.mark.asyncio
@pytest.mark.parametrize('file_path,method', TEST_FILES_METHODS)
async def test_get_response_for_file_returns_not_modified_handling_if_none_match_header(file_path, method):
    info = FileInfo.from_path(file_path)

    response = get_response_for_file(FilesHandler(),
                                     Request(method, b'/example',
                                             [(b'If-None-Match', info.etag.encode())]),
                                     file_path,
                                     1200)

    assert response.status == 304
    data = await response.read()
    assert data is None


@pytest.mark.asyncio
@pytest.mark.parametrize('file_path', TEST_FILES)
async def test_get_response_for_file_with_head_method_returns_empty_body_with_info(file_path):
    response = get_response_for_file(FilesHandler(),
                                     Request('HEAD', b'/example', None),
                                     file_path,
                                     1200)

    assert response.status == 200
    data = await response.read()
    assert data is None


@pytest.mark.asyncio
@pytest.mark.parametrize('cache_time', [
    100,
    500,
    1200
])
async def test_get_response_for_file_returns_cache_control_header(cache_time):
    response = get_response_for_file(FilesHandler(),
                                     Request('GET', b'/example', None),
                                     TEST_FILES[0],
                                     cache_time)

    assert response.status == 200
    header = response.get_single_header(b'cache-control')

    assert header == f'max-age={cache_time}'.encode()


@pytest.mark.asyncio
@pytest.mark.parametrize('range_value,expected_bytes,expected_content_range', [
    [b'bytes=0-10', b'Lorem ipsu', b'bytes 0-10/447'],
    [b'bytes=10-20', b'm dolor si', b'bytes 10-20/447'],
    [b'bytes=33-44', b'ctetur adip', b'bytes 33-44/447'],
    [b'bytes=15-50', b'or sit amet, consectetur adipiscing', b'bytes 15-50/447'],
    [b'bytes=66-', b'usmod tempor incididunt ut labore et dolore magna\naliqua. Ut enim ad minim veniam, quis nostrud '
                   b'exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis\n aute irure dolor in '
                   b'reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint\n '
                   b'occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.',
     b'bytes 66-446/447'],
    [b'bytes=381-',
     b'nt, sunt in culpa qui officia deserunt mollit anim id est laborum.',
     b'bytes 381-446/447'],
    [b'bytes=-50', b'a qui officia deserunt mollit anim id est laborum.',
     b'bytes 397-446/447'],
    [b'bytes=-66', b'nt, sunt in culpa qui officia deserunt mollit anim id est laborum.',
     b'bytes 381-446/447']
])
async def test_text_file_range_request_single_part(range_value, expected_bytes, expected_content_range):
    file_path = _get_file_path('example.txt')
    response = get_response_for_file(FilesHandler(),
                                     Request('GET', b'/example',
                                             [(b'Range', range_value)]),
                                     file_path,
                                     1200)
    assert response.status == 206
    body = await response.read()
    assert body == expected_bytes

    assert response.get_single_header(b'content-range') == expected_content_range


@pytest.mark.asyncio
@pytest.mark.parametrize('range_value', [
    b'bytes=0-10000000000',
    b'bytes=100-200000',
    b'bytes=1111111111114-',
    b'bytes=-1111111111114'
])
async def test_invalid_range_request_range_not_satisfiable(range_value):
    file_path = _get_file_path('example.txt')
    with pytest.raises(RangeNotSatisfiable):
        get_response_for_file(FilesHandler(),
                              Request('GET', b'/example',
                                      [(b'Range', range_value)]),
                              file_path,
                              1200)


@pytest.mark.asyncio
@pytest.mark.parametrize('range_value,expected_bytes_lines', [
    [b'bytes=0-10, 10-20', [
        b'--##BOUNDARY##',
        b'Content-Type: text/plain',
        b'Content-Range: bytes 0-10/447',
        b'',
        b'Lorem ipsu',
        b'--##BOUNDARY##',
        b'Content-Type: text/plain',
        b'Content-Range: bytes 10-20/447',
        b'',
        b'm dolor si',
        b'--##BOUNDARY##--'
    ]],
    [b'bytes=0-10, -66', [
        b'--##BOUNDARY##',
        b'Content-Type: text/plain',
        b'Content-Range: bytes 0-10/447',
        b'',
        b'Lorem ipsu',
        b'--##BOUNDARY##',
        b'Content-Type: text/plain',
        b'Content-Range: bytes 381-446/447',
        b'',
        b'nt, sunt in culpa qui officia deserunt mollit anim id est laborum.',
        b'--##BOUNDARY##--'
    ]],
])
async def test_text_file_range_request_multi_part(range_value, expected_bytes_lines: bytes):
    file_path = _get_file_path('example.txt')
    response = get_response_for_file(FilesHandler(),
                                     Request('GET', b'/example',
                                             [(b'Range', range_value)]),
                                     file_path,
                                     1200)
    assert response.status == 206
    content_type = response.content.type
    boundary = content_type.split(b'=')[1]
    body = await response.read()

    expected_bytes_lines = [line.replace(b'##BOUNDARY##', boundary) for line in expected_bytes_lines]
    assert body.splitlines() == expected_bytes_lines


@pytest.mark.asyncio
@pytest.mark.parametrize('range_value,matches', [
    [b'bytes=0-10', True],
    [b'bytes=0-10', False],
    [b'bytes=10-20', True],
    [b'bytes=10-20', False]
])
async def test_text_file_range_request_single_part_if_range_handling(range_value, matches):
    file_path = _get_file_path('example.txt')
    info = FileInfo.from_path(file_path)

    response = get_response_for_file(FilesHandler(),
                                     Request('GET', b'/example',
                                             [(b'Range', range_value),
                                              (b'If-Range', info.etag.encode()
                                               + (b'' if matches else b'xx'))]),
                                     file_path,
                                     1200)

    expected_status = 206 if matches else 200

    assert response.status == expected_status

    if not matches:
        body = await response.read()

        with open(file_path, mode='rb') as actual_file:
            assert body == actual_file.read()
