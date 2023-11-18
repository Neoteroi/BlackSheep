import asyncio
import os
import pathlib
from multiprocessing import Process
from time import sleep

import pytest

from blacksheep.client import ClientSession
from blacksheep.client.pool import ConnectionPools
from itests.utils import get_sleep_time

from .flask_app import app


def get_static_path(file_name):
    static_folder_path = pathlib.Path(__file__).parent.absolute() / "static"
    return os.path.join(str(static_folder_path), file_name.lstrip("/"))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for all test cases."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def server_host():
    return "127.0.0.1"


@pytest.fixture(scope="module")
def server_port():
    return 44777


@pytest.fixture(scope="module")
def server_url(server_host, server_port):
    return f"http://{server_host}:{server_port}"


@pytest.fixture(scope="module")
def session(server_url, event_loop):
    # It is important to pass the instance of ConnectionPools,
    # to ensure that the connections are reused and closed
    session = ClientSession(
        loop=event_loop,
        base_url=server_url,
        pools=ConnectionPools(event_loop),
    )
    yield session
    asyncio.run(session.close())


@pytest.fixture(scope="module")
def session_alt(event_loop):
    session = ClientSession(
        loop=event_loop,
        default_headers=[(b"X-Default-One", b"AAA"), (b"X-Default-Two", b"BBB")],
    )
    yield session
    event_loop.run_until_complete(session.close())


def start_server():
    print("[*] Flask app listening on 0.0.0.0:44777")
    app.run(host="127.0.0.1", port=44777)


@pytest.fixture(scope="module", autouse=True)
def server(server_host, server_port):
    server_process = Process(target=start_server)
    server_process.start()
    sleep(get_sleep_time())

    yield 1

    sleep(1.2)
    server_process.terminate()
