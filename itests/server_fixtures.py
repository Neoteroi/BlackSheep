import asyncio
import os
import socket
from multiprocessing import Process
from time import sleep

import pytest
import uvicorn
from hypercorn.asyncio import serve as hypercorn_serve
from hypercorn.run import Config as HypercornConfig

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


def _start_server(target_app, port: int):
    server_type = os.environ.get("ASGI_SERVER", "uvicorn")

    if server_type == "uvicorn":
        uvicorn.run(target_app, host="127.0.0.1", port=port, log_level="debug")
    elif server_type == "hypercorn":
        config = HypercornConfig()
        config.bind = [f"localhost:{port}"]
        config.loglevel = "DEBUG"
        asyncio.run(hypercorn_serve(target_app, config))
    else:
        raise ValueError(f"unsupported server type {server_type}")


def start_server_1():
    _start_server(app, 44555)


def start_server_2():
    _start_server(app_two, 44556)


def _start_server_process(target):
    server_process = Process(target=target)
    server_process.start()
    sleep(get_sleep_time())

    if not server_process.is_alive():
        raise TypeError("The server process did not start!")

    yield 1

    sleep(1.2)
    server_process.terminate()


@pytest.fixture(scope="module", autouse=True)
def server():
    yield from _start_server_process(start_server_1)


@pytest.fixture(scope="module", autouse=True)
def server_two():
    yield from _start_server_process(start_server_2)
