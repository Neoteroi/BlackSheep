import os
import pathlib
import asyncio
from multiprocessing import Process
from time import sleep

import pytest

from blacksheep.client import ClientSession

from .flask_app import app


def get_static_path(file_name):
    static_folder_path = pathlib.Path(__file__).parent.absolute() / 'static'
    return os.path.join(str(static_folder_path), file_name.lstrip('/'))


@pytest.fixture(scope='session')
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope='module')
def server_host():
    return '0.0.0.0'


@pytest.fixture(scope='module')
def server_port():
    return 44777


@pytest.fixture(scope='module')
def session(server_host, server_port, event_loop):
    session = ClientSession(loop=event_loop,
                            base_url=f'http://{server_host}:{server_port}')
    yield session
    asyncio.run(session.close())


@pytest.fixture(scope='module')
def session_alt(event_loop):
    session = ClientSession(loop=event_loop, default_headers=[
        (b'X-Default-One', b'AAA'),
        (b'X-Default-Two', b'BBB')
    ])
    yield session
    event_loop.run_until_complete(session.close())


@pytest.fixture(scope='module', autouse=True)
def server(server_host, server_port):
    def start_server():
        print(f'[*] Flask app listening on {server_host}:{server_port}')
        app.run(host=server_host, port=server_port)

    server_process = Process(target=start_server)
    server_process.start()
    sleep(0.5)

    yield 1

    sleep(1.2)
    server_process.terminate()
