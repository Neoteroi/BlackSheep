from uuid import uuid4

import pytest

from blacksheep.utils.aio import HTTPHandler

from .client_fixtures import *  # NoQA


@pytest.mark.asyncio
async def test_http_handler_fetch_plain_text(server_url):
    http_handler = HTTPHandler()

    for _ in range(5):
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
