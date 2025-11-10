from pydantic import BaseModel

from blacksheep.server.bindings import FromJSON
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend


class CustomClass:

    def __init__(self, obj) -> None:
        self.obj = obj


class Example(BaseModel):
    id: int
    name: str


class ExampleCollection(FromJSON[list[Example]]):

    @staticmethod
    def convert(obj) -> list[Example]:
        return [Example(**item) for item in obj]


class JSONNestedList(FromJSON[list[list[str]]]):

    @staticmethod
    def convert(obj) -> list[list[str]]:
        """
        This function is a custom converter for request bodies. It receives as input the
        already JSON-parsed Python object (not the raw JSON string), and can return any
        custom Python object as needed for your application logic.
        """
        # return the object as-is
        return obj


async def _post_scenario(app, request_body):
    await app(
        get_example_scope(
            "POST",
            "/",
            [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(request_body)).encode()),
            ],
        ),
        MockReceive([request_body]),
        MockSend(),
    )
    assert app.response.status == 204


async def test_custom_converter_in_class_definition_1(app):
    request_body = b'[["one","two"],["three"]]'
    expected_result = [["one", "two"], ["three"]]

    @app.router.post("/")
    async def home(item: JSONNestedList):
        assert item is not None
        value = item.value
        assert value == expected_result

    await _post_scenario(app, request_body)


async def test_custom_converter_in_class_definition_2(app):
    request_body = b'[{"id": 1, "name": "Hello"}, {"id": 2, "name": "World"}]'
    expected_result = [Example(id=1, name="Hello"), Example(id=2, name="World")]

    @app.router.post("/")
    async def home(item: FromJSON[list[Example]]):
        assert item is not None
        value = item.value
        assert value == expected_result

    await _post_scenario(app, request_body)


async def test_custom_class_handling(app):
    request_body = b'[["one","two"],["three"]]'
    expected_result = CustomClass([["one", "two"], ["three"]])

    @app.router.post("/")
    async def home(item: FromJSON[CustomClass]):
        assert item is not None
        assert isinstance(expected_result, CustomClass)
        assert expected_result.obj == expected_result.obj

    await _post_scenario(app, request_body)
