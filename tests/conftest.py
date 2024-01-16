import os

import pytest

from blacksheep.server.rendering.jinja2 import JinjaRenderer
from blacksheep.settings.html import html_settings
from tests.utils.application import FakeApplication

# configures default Jinja settings for tests
os.environ["APP_DEFAULT_ROUTER"] = "0"
os.environ["APP_JINJA_PACKAGE_NAME"] = "tests.testapp"
os.environ["APP_JINJA_PACKAGE_PATH"] = "templates"
os.environ["APP_SIGNAL_HANDLER"] = "0"


@pytest.fixture
def app():
    return FakeApplication()


ASYNC_RENDERER = JinjaRenderer(enable_async=True)


@pytest.fixture()
def async_jinja_env():
    """
    Configures an async renderer for a test (Jinja does not support synch and async
    rendering in the same environment).
    """
    default_renderer = html_settings.renderer
    html_settings._renderer = ASYNC_RENDERER
    yield True
    html_settings._renderer = default_renderer
