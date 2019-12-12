import pytest
import pkg_resources
from blacksheep import Request
from blacksheep.server.files.dynamic import get_response_for_file


def _get_file_path(file_name):
    return pkg_resources.resource_filename(__name__, './files/' + file_name)


def test_get_response_for_file_raise_for_file_not_found():
    with pytest.raises(FileNotFoundError):
        get_response_for_file(Request('GET', b'/example.txt', None),
                              'example.txt',
                              1200)


@pytest.mark.asyncio
@pytest.mark.parametrize('file_path', [
    'lorem-ipsum.txt',
    'example.txt',
    'pexels-photo-126407.jpeg'
])
async def test_get_response_for_file_returns_file_contents(file_path):
    file_path = _get_file_path(file_path)

    response = get_response_for_file(Request('GET', b'/' + file_path.encode(), None),
                                     file_path,
                                     1200)

    assert response.status == 200
    data = await response.read()

    with open(file_path, mode='rb') as test_file:
        contents = test_file.read()

    assert data == contents


@pytest.mark.asyncio
@pytest.mark.parametrize('cache_time', [
    100,
    500,
    1200
])
async def test_get_response_for_file_returns_cache_control_header(cache_time):
    file_path = _get_file_path('lorem-ipsum.txt')

    response = get_response_for_file(Request('GET', b'/' + file_path.encode(), None),
                                     file_path,
                                     cache_time)

    assert response.status == 200
    header = response.get_single_header(b'cache-control')

    assert header == f'max-age={cache_time}'.encode()


# TODO: test head request
# TODO: test returns etag
# TODO: test returns Accept-Ranges: bytes
# TODO: test returns content-type and length
# TODO: test handle if-none-match and not modified
# TODO: test handle if-range
# TODO: test handle range requests
# TODO: test RangeNotSatisfiable


