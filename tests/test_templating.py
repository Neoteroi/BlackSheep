from dataclasses import dataclass
from typing import List

import pytest
from pydantic import BaseModel

from blacksheep.server.controllers import Controller, RoutesRegistry
from blacksheep.server.rendering.jinja2 import get_template_name
from blacksheep.server.responses import view, view_async
from blacksheep.settings.html import html_settings
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from tests.utils.application import FakeApplication


def get_app(enable_async):
    app = FakeApplication()
    return app, view_async if enable_async else view


@pytest.fixture()
def home_model():
    return {
        "title": "Example",
        "heading": "Hello World!",
        "paragraph": "Lorem ipsum dolor sit amet",
    }


@dataclass
class Sentence:
    text: str
    url: str


@dataclass
class HelloModel:
    name: str
    sentences: List[Sentence]


class Sentence2:
    def __init__(self, text: str, url: str) -> None:
        self.text = text
        self.url = url


class HelloModel2:
    def __init__(self, name: str, sentences: List[Sentence2]) -> None:
        self.name = name
        self.sentences = sentences


class PydanticSentence(BaseModel):
    text: str
    url: str


class PydanticHelloModel(BaseModel):
    name: str
    sentences: List[PydanticSentence]


def dataclass_model():
    return HelloModel(
        "World!",
        [
            Sentence(
                "Check this out!",
                "https://github.com/Neoteroi/BlackSheep",
            )
        ],
    )


def class_model():
    return HelloModel2(
        "World!",
        [
            Sentence2(
                "Check this out!",
                "https://github.com/Neoteroi/BlackSheep",
            )
        ],
    )


def pydantic_model():
    return PydanticHelloModel(
        name="World!",
        sentences=[
            PydanticSentence(
                text="Check this out!",
                url="https://github.com/Neoteroi/BlackSheep",
            )
        ],
    )


@pytest.fixture()
def specific_text():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Specific Example</title>
</head>
<body>
    <h1>Hello World!</h1>
    <p>Lorem ipsum dolor sit amet</p>
</body>
</html>"""


nomodel_text = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Example</title>
</head>
<body>
    <h1>Hello World!</h1>
    <p>Lorem ipsum dolor sit amet</p>
</body>
</html>"""


async def _home_scenario(app: FakeApplication, url="/", expected_text=None):
    await app(get_example_scope("GET", url), MockReceive(), MockSend())
    text = await app.response.text()

    if expected_text is None:
        expected_text = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Example</title>
</head>
<body>
    <h1>Hello World!</h1>
    <p>Lorem ipsum dolor sit amet</p>
</body>
</html>"""

    assert text == expected_text
    assert app.response.status == 200


async def _view_scenario(app: FakeApplication, expected_text, url="/"):
    await app(get_example_scope("GET", url), MockReceive(), MockSend())
    text = await app.response.text()
    assert text == expected_text
    assert app.response.status == 200


async def test_jinja_async_mode(home_model, async_jinja_env):
    app, render = get_app(True)

    @app.router.get("/")
    async def home():
        return await render("home", home_model)

    await _home_scenario(app)


async def test_jinja_sync_mode(home_model):
    app, render = get_app(False)

    @app.router.get("/")
    async def home():
        return render("home", home_model)

    await _home_scenario(app)


async def test_controller_conventional_view_name(home_model):
    app, _ = get_app(False)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get()
        def index(self):
            return self.view(model=home_model)

    await _home_scenario(app)


async def test_controller_conventional_view_name_async(home_model, async_jinja_env):
    app, _ = get_app(True)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get()
        async def index(self):
            return await self.view_async(model=home_model)

    await _home_scenario(app)


async def test_controller_specific_view_name(home_model, specific_text):
    app, _ = get_app(False)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get()
        def index(self):
            return self.view("specific", home_model)

    await _home_scenario(app, expected_text=specific_text)


async def test_controller_specific_view_name_async(
    home_model, specific_text, async_jinja_env
):
    app, _ = get_app(True)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get()
        async def index(self):
            return await self.view_async("specific", model=home_model)

    await _home_scenario(app, expected_text=specific_text)


async def test_controller_specific_view_name_async_no_model(async_jinja_env):
    app, _ = get_app(True)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get()
        async def index(self):
            return await self.view_async("nomodel")

    await _home_scenario(app, expected_text=nomodel_text)


async def test_controller_conventional_view_name_no_model(home_model):
    app, _ = get_app(False)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get(...)
        def nomodel(self):
            return self.view()

    await _home_scenario(app, "/nomodel", expected_text=nomodel_text)


async def test_controller_conventional_view_name_sub_function(home_model):
    app, _ = get_app(False)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        def ufo(self, model):
            return self.foo(model)

        def foo(self, model):
            return self.view(model=model)

        @get()
        def index(self):
            return self.ufo(home_model)

    await _home_scenario(app)


async def test_controller_conventional_view_name_extraneous_function(home_model):
    app, _ = get_app(False)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    def extraneous(controller, model):
        return controller.view(model=model)

    class Lorem(Controller):
        def ufo(self, model):
            return self.foo(model)

        def foo(self, model):
            return extraneous(self, model)

        @get()
        def index(self):
            return self.ufo(home_model)

    await _home_scenario(app)


@pytest.mark.parametrize(
    "value,expected_name",
    [
        ("index", "index.jinja"),
        ("index.jinja", "index.jinja"),
        ("default", "default.jinja"),
    ],
)
def test_template_name(value, expected_name):
    assert get_template_name(value) == expected_name


@pytest.mark.parametrize(
    "model_fixture",
    [
        class_model,
        dataclass_model,
        pydantic_model,
    ],
)
async def test_controller_model_interop(model_fixture):
    app, _ = get_app(False)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get()
        def index(self):
            return self.view("hello", model_fixture())

    await _view_scenario(
        app,
        expected_text='<div style="margin: 10em 2em;">\n  <h1>Hello, World!!</h1>\n\n'
        + '  <ul>\n    \n      <li><a href="https://github.com/Neoteroi/'
        + 'BlackSheep">Check this out!</a></li>\n    \n  </ul>\n</div>',
    )


def test_model_to_view_params_passes_unhandled_argument():
    assert html_settings.model_to_params(2) == 2
    assert html_settings.model_to_params("Something") == "Something"
