import pytest

from blacksheep.client import ClientSession, ConnectionTimeout, RequestTimeout

from . import FakePools


async def test_connection_timeout():
    fake_pools = FakePools([])
    fake_pools.pool.sleep_for = (
        5  # wait for 5 seconds before returning a connection; to test timeout handling
    )

    async with ClientSession(
        base_url=b"http://localhost:8080",
        pools=fake_pools,
        connection_timeout=0.002,  # 2ms - not realistic, but ok for this test
    ) as client:
        with pytest.raises(ConnectionTimeout):
            await client.get(b"/")


async def test_request_timeout():
    fake_pools = FakePools([])
    fake_pools.pool.connection.sleep_for = (
        5  # wait for 5 seconds before returning a response;
    )

    async with ClientSession(
        base_url=b"http://localhost:8080",
        pools=fake_pools,
        request_timeout=0.002,  # 2ms - not realistic, but ok for this test
    ) as client:
        with pytest.raises(RequestTimeout):
            await client.get(b"/")
