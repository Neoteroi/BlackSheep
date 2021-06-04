from typing import Dict, Optional

import pytest

from blacksheep import Content
from blacksheep.contents import JSONContent
from blacksheep.server.application import Application
from blacksheep.server.bindings import FromHeader
from blacksheep.server.responses import Response
from blacksheep.testing import AbstractTestSimulator, TestClient


class CustomTestSimulator(AbstractTestSimulator):
    async def send_request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query: Optional[Dict[str, str]] = b"",
        content: Optional[Content] = None,
    ):
        if method == "GET":
            return {"custom": "true"}


async def _start_application(app):
    await app.start()


@pytest.fixture
def test_app():
    return Application(show_error_details=True)


@pytest.mark.asyncio
async def test_client_response(test_app):
    @test_app.route("/")
    async def home(request):
        return {"foo": "bar"}

    await _start_application(test_app)

    test_client = TestClient(test_app)
    response = await test_client.get("/")

    actual_json_body = await response.json()
    expected_body = {"foo": "bar"}

    assert isinstance(response, Response)
    assert actual_json_body == expected_body


@pytest.mark.asyncio
async def test_client_headers(test_app):
    class FromTestHeader(FromHeader[str]):
        name = "test_header"

    @test_app.route("/")
    async def home(request, test_header: FromTestHeader):
        return test_header.value

    await _start_application(test_app)

    test_client = TestClient(test_app)
    response = await test_client.get("/", headers={"test_header": "foo"})

    actual_header_value = await response.text()
    expected_header_value = "foo"

    assert actual_header_value == expected_header_value


@pytest.mark.asyncio
async def test_client_content(test_app):
    @test_app.route("/", methods=["POST"])
    async def home(request):
        json_data = await request.json()
        return json_data

    await _start_application(test_app)

    test_client = TestClient(test_app)
    response = await test_client.post("/", content=JSONContent({"foo": "bar"}))

    actual_json_response = await response.json()
    expected_json_response = {"foo": "bar"}

    assert actual_json_response == expected_json_response


@pytest.mark.asyncio
async def test_client_queries(test_app):
    @test_app.route("/")
    async def home(request):
        return request.query

    await _start_application(test_app)

    test_client = TestClient(test_app)
    response = await test_client.get("/", query={"foo": "bar"})

    actual_response = await response.json()
    expected_response = {"foo": ["bar"]}

    assert actual_response == expected_response


@pytest.mark.asyncio
async def test_client_content_raise_error_if_incorrect_type(test_app):
    with pytest.raises(ValueError):
        await _start_application(test_app)

        test_client = TestClient(test_app)

        await test_client.post("/", content={"foo": "bar"})


@pytest.mark.asyncio
async def test_client_application_not_started_error(test_app):
    with pytest.raises(AssertionError):
        TestClient(test_app)


@pytest.mark.asyncio
async def test_custom_test_simulator(test_app):
    test_client = TestClient(test_app, test_simulator=CustomTestSimulator())

    actual_response = await test_client.get("/")
    expected_response = {"custom": "true"}

    assert actual_response == expected_response


@pytest.mark.parametrize(
    "method, expected_method",
    [
        ("GET", "GET"),
        ("POST", "POST"),
        ("PATCH", "PATCH"),
        ("PUT", "PUT"),
        ("DELETE", "DELETE"),
    ],
)
@pytest.mark.asyncio
async def test_client_methods(test_app, method, expected_method):
    @test_app.route("/", methods=[method])
    async def home(request):
        return request.method

    await _start_application(test_app)

    client = TestClient(test_app)
    response = await getattr(client, method.lower())("/")

    actual_method = await response.text()

    assert actual_method == expected_method
