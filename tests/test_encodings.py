from dataclasses import dataclass

from blacksheep.server.responses import ok
from blacksheep.server.routing import Router
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from tests.utils.application import FakeApplication


@dataclass
class Cat:
    id: int
    name: str


async def test_application_encoding_error_1():
    app = FakeApplication(router=Router())

    @app.router.post("/")
    def home(data: Cat):
        return ok(data)

    # Simulate a request where the client declares a wrong encoding
    # the payload is encoded using ISO-8859-1 but the client declares UTF-8
    scope = get_example_scope(
        "POST",
        "/",
        [(b"Content-Type", b"Content-Type: application/json; charset=UTF-8")],
    )

    await app(
        scope,
        MockReceive(['{"id": 1, "name": "Café"}'.encode("ISO-8859-1")]),
        MockSend(),
    )

    response = app.response
    # Response status is Bad Request 400
    assert response is not None
    assert response.status == 400
    # The response body contains useful information
    text = await response.text()
    assert "Cannot decode the request content using: utf-8." in text


async def test_application_encoding_correct_1():
    app = FakeApplication(router=Router())

    @app.router.post("/")
    def home(data: Cat):
        return ok(data)

    # Simulate a request where the client declares properly an encoding different than
    # UTF-8
    scope = get_example_scope(
        "POST",
        "/",
        [(b"Content-Type", b"Content-Type: application/json; charset=ISO-8859-1")],
    )

    await app(
        scope,
        MockReceive(['{"id": 1, "name": "Café"}'.encode("ISO-8859-1")]),
        MockSend(),
    )

    response = app.response

    assert response is not None
    assert response.status == 200
    # The response body contains useful information
    text = await response.text()
    assert '{"id":1,"name":"Café"}' == text
