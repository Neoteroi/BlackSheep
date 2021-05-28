import pytest

from blacksheep.server.application import Application
from blacksheep.server.bindings import FromHeader
from blacksheep.contents import JSONContent
from blacksheep.server.responses import Response
from blacksheep.testing import TestClient


@pytest.fixture
def test_app():
    return Application(show_error_details=True)


@pytest.mark.asyncio
async def test_client_response(test_app):
    @test_app.route("/")
    async def home(request):
        return {"foo": "bar"}

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

    test_client = TestClient(test_app)
    response = await test_client.get("/", query={"foo": "bar"})

    actual_response = await response.json()
    expected_response = {"foo": ["bar"]}

    assert actual_response == expected_response


@pytest.mark.asyncio
async def test_client_content_raise_error_if_incorrect_type(test_app):
    with pytest.raises(ValueError):
        test_client = TestClient(test_app)
        await test_client.post("/", content={"foo": "bar"})
