import os
import socket
from multiprocessing import Process
from time import sleep

import pytest
import uvicorn

from .app import app
from .app_two import app_two
from .utils import ClientSession, get_sleep_time


@pytest.fixture(scope="module")
def server_host():
    return "127.0.0.1"


@pytest.fixture(scope="module")
def server_port():
    return 44555


@pytest.fixture(scope="module")
def server_port_two():
    return 44556


@pytest.fixture()
def socket_connection(server_port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
    s.connect(("localhost", server_port))
    yield s
    s.close()


@pytest.fixture(scope="module")
def session(server_host, server_port):
    return ClientSession(f"http://{server_host}:{server_port}")


@pytest.fixture(scope="module")
def session_two(server_host, server_port_two):
    return ClientSession(f"http://{server_host}:{server_port_two}")


def start_server():
    uvicorn.run(app, host="127.0.0.1", port=44555, log_level="debug")


def start_server2():
    uvicorn.run(app_two, host="127.0.0.1", port=44556, log_level="debug")


@pytest.fixture(scope="module", autouse=True)
def server(server_host, server_port):
    server_process = Process(target=start_server)
    server_process.start()
    sleep(get_sleep_time())

    yield 1

    sleep(1.2)
    server_process.terminate()


@pytest.fixture(scope="module", autouse=True)
def server_two(server_host, server_port_two):
    server_process = Process(target=start_server2)
    server_process.start()
    sleep(1.5)

    yield 1

    sleep(1.2)
    server_process.terminate()
