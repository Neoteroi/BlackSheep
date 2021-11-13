import ssl

import pytest

from blacksheep.client.connection import (
    INSECURE_SSLCONTEXT,
    SECURE_SSLCONTEXT,
    ClientConnection,
)
from blacksheep.client.pool import ClientConnectionPool, get_ssl_context
from blacksheep.exceptions import InvalidArgument

from blacksheep.utils.aio import get_running_loop

example_context = ssl.SSLContext()
example_context.check_hostname = False


@pytest.mark.parametrize(
    "scheme,ssl_option,expected_result",
    [
        (b"https", False, INSECURE_SSLCONTEXT),
        (b"https", True, SECURE_SSLCONTEXT),
        (b"https", None, SECURE_SSLCONTEXT),
        (b"https", example_context, example_context),
    ],
)
def test_get_ssl_context(scheme, ssl_option, expected_result):
    assert get_ssl_context(scheme, ssl_option) is expected_result


def test_get_ssl_context_raises_for_http():
    with pytest.raises(InvalidArgument):
        get_ssl_context(b"http", True)

    with pytest.raises(InvalidArgument):
        get_ssl_context(b"http", SECURE_SSLCONTEXT)


def test_get_ssl_context_raises_for_invalid_argument():
    with pytest.raises(InvalidArgument):
        get_ssl_context(b"https", 1)  # type: ignore

    with pytest.raises(InvalidArgument):
        get_ssl_context(b"https", {})  # type: ignore


def test_return_connection_disposed_pool_does_nothing():
    pool = ClientConnectionPool(get_running_loop(), b"http", b"foo.com", 80, None)

    pool.dispose()
    pool.try_return_connection(ClientConnection(pool.loop, pool))


def test_return_connection_does_nothing_if_the_queue_is_full():
    pool = ClientConnectionPool(
        get_running_loop(), b"http", b"foo.com", 80, None, max_size=2
    )

    for i in range(5):
        pool.try_return_connection(ClientConnection(pool.loop, pool))

        if i + 1 >= 2:
            assert pool._idle_connections.full() is True
