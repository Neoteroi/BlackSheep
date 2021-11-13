from datetime import datetime
from typing import Any

import pytest
from guardpost import User

from blacksheep.messages import Request, Response
from blacksheep.server.authentication.cookie import CookieAuthentication
from blacksheep.server.dataprotection import generate_secret


def get_auth_cookie(handler: CookieAuthentication, data: Any) -> str:
    response = Response(200)
    handler.set_cookie(data, response)
    return handler.cookie_name + "=" + response.cookies[handler.cookie_name].value


@pytest.mark.asyncio
async def test_cookie_authentication():
    handler = CookieAuthentication()

    request = Request("GET", b"/", headers=[])

    await handler.authenticate(request)

    assert request.identity is not None
    assert request.identity.is_authenticated() is False

    request = Request(
        "GET",
        b"/",
        headers=[
            (
                b"cookie",
                get_auth_cookie(
                    handler, {"id": 1, "email": "example@neoteroi.dev"}
                ).encode(),
            )
        ],
    )

    await handler.authenticate(request)

    assert isinstance(request.identity, User)
    assert request.identity.is_authenticated() is True
    assert request.identity.authentication_mode == handler.auth_scheme
    assert request.identity.email == "example@neoteroi.dev"


@pytest.mark.asyncio
async def test_cookie_authentication_handles_invalid_signature():
    handler = CookieAuthentication()

    request = Request(
        "GET",
        b"/",
        headers=[
            (
                b"cookie",
                get_auth_cookie(
                    handler, {"id": 1, "email": "example@neoteroi.dev"}
                ).encode(),
            )
        ],
    )

    other_handler = CookieAuthentication(secret_keys=[generate_secret()])
    await other_handler.authenticate(request)

    assert request.identity is not None
    assert request.identity.is_authenticated() is False


def test_cookie_authentication_unset_cookie():
    handler = CookieAuthentication()

    response = Response(200)
    handler.unset_cookie(response)

    cookie_header = response.cookies[handler.cookie_name]
    assert cookie_header is not None
    assert cookie_header.expires is not None
    assert cookie_header.expires < datetime.utcnow()
