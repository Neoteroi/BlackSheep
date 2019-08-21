import pytest
import asyncio
from time import sleep
from multiprocessing import Process
from blacksheep.client import ClientSession
from .flask_app import app


@pytest.fixture(scope='session')
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope='module')
def server_host():
    return '0.0.0.0'
    # return '127.0.0.1'


@pytest.fixture(scope='module')
def server_port():
    return 44777


@pytest.fixture(scope='module')
def session(server_host, server_port, event_loop):
    session = ClientSession(loop=event_loop, base_url=f'http://{server_host}:{server_port}')
    yield session
    asyncio.run(session.close())


@pytest.fixture(scope='module')
def session_alt(event_loop):
    # TODO: default headers,
    # TODO: no base url
    session = ClientSession(loop=event_loop)
    yield session
    session.close()


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
