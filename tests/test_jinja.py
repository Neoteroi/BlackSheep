from blacksheep.server import Application
import pytest
from jinja2 import PackageLoader

from blacksheep.server.controllers import Controller, RoutesRegistry
from blacksheep.server.templating import use_templates, view, view_async, template_name

from .test_application import FakeApplication, MockReceive, MockSend, get_example_scope


def get_app(enable_async):
    app = FakeApplication()
    render = use_templates(
        app,
        loader=PackageLoader("tests.testapp", "templates"),
        enable_async=enable_async,
    )
    return app, render


@pytest.fixture()
def home_model():
    return {
        "title": "Example",
        "heading": "Hello World!",
        "paragraph": "Lorem ipsum dolor sit amet",
    }


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
    app.build_services()
    app.normalize_handlers()
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


@pytest.mark.asyncio
async def test_jinja_async_mode(home_model):
    app, render = get_app(True)

    @app.router.get(b"/")
    async def home():
        return await render("home", home_model)

    await _home_scenario(app)


@pytest.mark.asyncio
async def test_jinja_async_mode_named_parameters(home_model):
    app, render = get_app(True)

    @app.router.get(b"/")
    async def home():
        return await render("home", **home_model)

    await _home_scenario(app)


@pytest.mark.asyncio
async def test_jinja_sync_mode(home_model):
    app, render = get_app(False)

    @app.router.get(b"/")
    async def home():
        return render("home", home_model)

    await _home_scenario(app)


@pytest.mark.asyncio
async def test_jinja_sync_mode_named_parameters(home_model):
    app, render = get_app(False)

    @app.router.get(b"/")
    async def home():
        return render("home", **home_model)

    await _home_scenario(app)


@pytest.mark.asyncio
async def test_jinja_async_mode_with_verbose_method(home_model):
    app, _ = get_app(True)

    @app.router.get(b"/")
    async def home(jinja):
        return await view_async(jinja, "home", home_model)

    await _home_scenario(app)


@pytest.mark.asyncio
async def test_jinja_sync_mode_with_verbose_method(home_model):
    app, _ = get_app(False)

    @app.router.get(b"/")
    async def home(jinja):
        return view(jinja, "home", home_model)

    await _home_scenario(app)


@pytest.mark.asyncio
async def test_jinja_async_mode_with_verbose_method_named_parameters(home_model):
    app, _ = get_app(True)

    @app.router.get(b"/")
    async def home(jinja):
        return await view_async(jinja, "home", **home_model)

    await _home_scenario(app)


@pytest.mark.asyncio
async def test_jinja_sync_mode_with_verbose_method_named_parameters(home_model):
    app, _ = get_app(False)

    @app.router.get(b"/")
    async def home(jinja):
        return view(jinja, "home", **home_model)

    await _home_scenario(app)


@pytest.mark.asyncio
async def test_controller_conventional_view_name(home_model):
    app, _ = get_app(False)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get()
        def index(self):
            return self.view(model=home_model)

    app.setup_controllers()

    await _home_scenario(app)


@pytest.mark.asyncio
async def test_controller_conventional_view_name_async(home_model):
    app, _ = get_app(True)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get()
        async def index(self):
            return await self.view_async(model=home_model)

    app.setup_controllers()
    await _home_scenario(app)


@pytest.mark.asyncio
async def test_controller_specific_view_name(home_model, specific_text):
    app, _ = get_app(False)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get()
        def index(self):
            return self.view("specific", home_model)

    app.setup_controllers()

    await _home_scenario(app, expected_text=specific_text)


@pytest.mark.asyncio
async def test_controller_specific_view_name_async(home_model, specific_text):
    app, _ = get_app(True)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get()
        async def index(self):
            return await self.view_async("specific", model=home_model)

    app.setup_controllers()
    await _home_scenario(app, expected_text=specific_text)


@pytest.mark.asyncio
async def test_controller_specific_view_name_async_no_model():
    app, _ = get_app(True)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get()
        async def index(self):
            return await self.view_async("nomodel")

    app.setup_controllers()
    await _home_scenario(app, expected_text=nomodel_text)


@pytest.mark.asyncio
async def test_controller_conventional_view_name_no_model(home_model):
    app, _ = get_app(False)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get(...)
        def nomodel(self):
            return self.view()

    app.setup_controllers()

    await _home_scenario(app, "/nomodel", expected_text=nomodel_text)


@pytest.mark.asyncio
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

    app.setup_controllers()

    await _home_scenario(app)


@pytest.mark.asyncio
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

    app.setup_controllers()

    await _home_scenario(app)


@pytest.mark.parametrize(
    "value,expected_name",
    [
        ("index", "index.html"),
        ("index.html", "index.html"),
        ("default", "default.html"),
    ],
)
def test_template_name(value, expected_name):
    assert template_name(value) == expected_name


def test_use_templates_throws_for_invalid_services():
    app = Application(services={})  # type: ignore

    with pytest.raises(TypeError):
        use_templates(
            app, loader=PackageLoader("tests.testapp", "templates"), enable_async=False
        )
