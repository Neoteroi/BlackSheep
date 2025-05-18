import asyncio
import os
import socket
import multiprocessing
from multiprocessing import Process
from time import sleep

import pytest
import uvicorn
from hypercorn.asyncio import serve as hypercorn_serve
from hypercorn.run import Config as HypercornConfig

from .app_1 import app
from .app_2 import app_2
from .app_3 import app_3
from .app_4 import app_4, configure_json_settings
from .utils import ClientSession, get_sleep_time


multiprocessing.set_start_method("spawn", force=True)


@pytest.fixture(scope="module")
def server_host():
    return "127.0.0.1"


@pytest.fixture(scope="module")
def server_port_1():
    return 44555


@pytest.fixture(scope="module")
def server_port_2():
    return 44556


@pytest.fixture(scope="module")
def server_port_3():
    return 44557


@pytest.fixture(scope="module")
def server_port_4():
    return 44558


@pytest.fixture()
def socket_connection(server_port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
    s.connect(("localhost", server_port))
    yield s
    s.close()


@pytest.fixture(scope="module")
def session_1(server_host, server_port_1):
    return ClientSession(f"http://{server_host}:{server_port_1}")


@pytest.fixture(scope="module")
def session_2(server_host, server_port_2):
    return ClientSession(f"http://{server_host}:{server_port_2}")


@pytest.fixture(scope="module")
def session_3(server_host, server_port_3):
    return ClientSession(f"http://{server_host}:{server_port_3}")


@pytest.fixture(scope="module")
def session_4(server_host, server_port_4):
    return ClientSession(f"http://{server_host}:{server_port_4}")


def _start_server(target_app, port: int, init_callback=None):
    if init_callback is not None:
        init_callback()

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
    _start_server(app_2, 44556)


def start_server_3():
    _start_server(app_3, 44557)


def start_server_4():
    # Important: leverages process forking to configure JSON settings only in the
    # process running the app_4 application - this is important to not change
    # global settings for the whole tests suite
    _start_server(app_4, 44558, configure_json_settings)


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
def server_1():
    yield from _start_server_process(start_server_1)


@pytest.fixture(scope="module", autouse=True)
def server_2():
    yield from _start_server_process(start_server_2)


@pytest.fixture(scope="module", autouse=True)
def server_3():
    yield from _start_server_process(start_server_3)


@pytest.fixture(scope="module", autouse=True)
def server_4():
    yield from _start_server_process(start_server_4)
