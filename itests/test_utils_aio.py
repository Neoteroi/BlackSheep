from uuid import uuid4

import pytest

from blacksheep.utils.aio import (
    FailedRequestError,
    HTTPHandler,
    _try_parse_content_as_json,
)

from .client_fixtures import *  # NoQA


@pytest.mark.asyncio
async def test_http_handler_fetch_plain_text(server_url):
    http_handler = HTTPHandler()
    response = await http_handler.fetch(f"{server_url}/hello-world")
    assert response == b"Hello, World!"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        {"name": "Gorun Nova", "type": "Sword"},
        {"id": str(uuid4()), "price": "15.15", "name": "Ravenclaw T-Shirt"},
    ],
)
async def test_http_handler_post_form(server_url, data):
    http_handler = HTTPHandler()

    response = await http_handler.post_form(f"{server_url}/echo-posted-form", data)

    assert response == data


@pytest.mark.asyncio
async def test_http_handler_post_form_failure(server_url):
    http_handler = HTTPHandler()

    with pytest.raises(FailedRequestError) as request_error:
        await http_handler.post_form(f"{server_url}/not-existing", {})

    assert request_error.value.status >= 400


@pytest.mark.asyncio
async def test_http_handler_fetch_json(server_url):
    http_handler = HTTPHandler()
    response = await http_handler.fetch_json(f"{server_url}/plain-json")
    assert response == {"message": "Hello, World!"}


@pytest.mark.asyncio
async def test_http_handler_fetch_json_failed_request(server_url):
    http_handler = HTTPHandler()

    with pytest.raises(FailedRequestError) as failed_request_error:
        await http_handler.fetch(f"{server_url}/plain-json-error-simulation")

    assert failed_request_error.value.data == {"message": "Hello, World!"}


def test_try_parse_content_as_json():
    assert _try_parse_content_as_json(b"foo") == b"foo"
