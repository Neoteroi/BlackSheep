import pytest
from jinja2 import PackageLoader
from blacksheep.server.templating import use_templates, view, view_async
from .test_application import FakeApplication, get_new_connection_handler


def get_app(enable_async):
    app = FakeApplication()
    render = use_templates(app, loader=PackageLoader('tests.testapp', 'templates'), enable_async=enable_async)

    return app, render


@pytest.fixture()
def home_model():
    return {'title': 'Example',
            'heading': 'Hello World!',
            'paragraph': 'Lorem ipsum dolor sit amet'}


async def _home_scenario(app: FakeApplication):
    app.normalize_handlers()
    handler = get_new_connection_handler(app)

    handler.data_received(b'GET / HTTP/1.1\r\n\r\n')

    await app.response_done.wait()
    assert app.response.status == 200

    text = await app.response.text()
    assert text == """<!DOCTYPE html>
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


@pytest.mark.asyncio
async def test_jinja_async_mode(home_model):
    app, render = get_app(True)

    @app.router.get(b'/')
    async def home():
        return await render('home', home_model)
    await _home_scenario(app)


@pytest.mark.asyncio
async def test_jinja_async_mode_named_parameters(home_model):
    app, render = get_app(True)

    @app.router.get(b'/')
    async def home():
        return await render('home', **home_model)
    await _home_scenario(app)


@pytest.mark.asyncio
async def test_jinja_sync_mode(home_model):
    app, render = get_app(False)

    @app.router.get(b'/')
    async def home():
        return render('home', home_model)
    await _home_scenario(app)


@pytest.mark.asyncio
async def test_jinja_sync_mode_named_parameters(home_model):
    app, render = get_app(False)

    @app.router.get(b'/')
    async def home():
        return render('home', **home_model)
    await _home_scenario(app)


@pytest.mark.asyncio
async def test_jinja_async_mode_with_verbose_method(home_model):
    app, _ = get_app(True)

    @app.router.get(b'/')
    async def home(request):
        return await view_async(request, 'home', home_model)
    await _home_scenario(app)


@pytest.mark.asyncio
async def test_jinja_sync_mode_with_verbose_method(home_model):
    app, _ = get_app(False)

    @app.router.get(b'/')
    async def home(request):
        return view(request, 'home', home_model)
    await _home_scenario(app)


@pytest.mark.asyncio
async def test_jinja_async_mode_with_verbose_method_named_parameters(home_model):
    app, _ = get_app(True)

    @app.router.get(b'/')
    async def home(request):
        return await view_async(request, 'home', **home_model)
    await _home_scenario(app)


@pytest.mark.asyncio
async def test_jinja_sync_mode_with_verbose_method_named_parameters(home_model):
    app, _ = get_app(False)

    @app.router.get(b'/')
    async def home(request):
        return view(request, 'home', **home_model)
    await _home_scenario(app)
