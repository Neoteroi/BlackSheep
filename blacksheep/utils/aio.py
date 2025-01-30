import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from asyncio import AbstractEventLoop
from typing import Any, Optional


class FailedRequestError(Exception):
    def __init__(self, status, data) -> None:
        super().__init__(
            f"The response status code does not indicate success: {status}."
            if status > -1
            else "The request failed."
        )
        self.status = status
        self.data = data


def fetch(url: str) -> Any:
    try:
        with urllib.request.urlopen(url) as response:
            return response.read()
    except urllib.error.HTTPError as http_error:
        content = http_error.read()
        raise FailedRequestError(http_error.status, _try_parse_content_as_json(content))
    except urllib.error.URLError as url_error:
        # e.g. connection refused
        raise FailedRequestError(-1, str(url_error))


def _try_parse_content_as_json(content: bytes) -> Any:
    try:
        return json.loads(content.decode("utf8"))
    except json.JSONDecodeError:
        return content


def post(url: str, data) -> Any:
    raw_data = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url,
        method="POST",
        data=raw_data,
    )
    try:
        response = urllib.request.urlopen(req)
        content = response.read()
    except urllib.error.HTTPError as http_error:
        content = http_error.read()
        raise FailedRequestError(http_error.status, _try_parse_content_as_json(content))
    return _try_parse_content_as_json(content)


class HTTPHandler:
    def __init__(self, loop: Optional[AbstractEventLoop] = None) -> None:
        self._loop = loop

    @property
    def loop(self) -> AbstractEventLoop:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return self._loop

    async def fetch(self, url: str) -> Any:
        return await self.loop.run_in_executor(None, lambda: fetch(url))

    async def fetch_json(self, url: str) -> Any:
        data = await self.fetch(url)
        return json.loads(data)

    async def post_form(self, url: str, data: Any) -> Any:
        return await self.loop.run_in_executor(None, lambda: post(url, data))


def get_running_loop() -> AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        # TODO: fix deprecation warning happening in the test suite
        # DeprecationWarning: There is no current event loop
        return asyncio.get_event_loop()
