import errno
import os
import socket
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urljoin

import requests

from .logs import get_logger

logger = get_logger()


class ClientSession(requests.Session):
    def __init__(self, base_url):
        self.base_url = base_url
        super().__init__()

    def request(self, method, url, *args, **kwargs):
        return super().request(method, urljoin(self.base_url, url), *args, **kwargs)


class CrashTest(Exception):
    def __init__(self):
        super().__init__("Crash Test!")


def ensure_success(response):
    if response.status_code != 200:
        text = response.text
        logger.error(text)

    assert response.status_code == 200


def get_connection(host: str, port: int):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    return s


def ensure_folder(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def assert_files_equals(path_one, path_two):
    with open(path_one, mode="rb") as one, open(path_two, mode="rb") as two:
        chunk_one = one.read(1024)
        chunk_two = two.read(1024)

        assert chunk_one == chunk_two


def assert_file_content_equals(file_path, content):
    with open(file_path, mode="rt", encoding="utf8") as file:
        file_contents = file.read()
        assert file_contents == content


def get_file_bytes(file_path):
    with open(file_path, mode="rb") as file:
        return file.read()


def get_sleep_time():
    # when starting a server process,
    # a longer sleep time is necessary on Windows
    if os.name == "nt":
        return 1.5
    return 0.5


def get_test_files_url(url: str):
    return f"my-cdn-foo:{url}"


@contextmanager
def temp_file(name: str):
    file = Path(name)
    if file.exists():
        file.unlink()

    yield file

    if file.exists():
        file.unlink()
