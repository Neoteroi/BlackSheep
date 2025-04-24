import re

import pytest

from blacksheep.contents import write_www_form_urlencoded
from blacksheep.messages import Response
from blacksheep.server.controllers import Controller
from blacksheep.server.csrf import ignore_anti_forgery, use_anti_forgery
from blacksheep.server.rendering.jinja2 import AntiForgeryBaseExtension, JinjaRenderer
from blacksheep.server.responses import no_content, view, view_async
from blacksheep.server.routing import RoutesRegistry
from blacksheep.settings.html import html_settings
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from tests.utils.application import FakeApplication


def read_control_value_from_input(text: str) -> str:
    match = re.search(r'name="__RequestVerificationToken" value="([^\"]+)"', text)

    assert match is not None
    return match.group(1)


def get_app(enable_async=False):
    app = FakeApplication()
    use_anti_forgery(app)
    return app, view_async if enable_async else view


@pytest.fixture()
def home_model():
    return {
        "title": "Example",
        "heading": "Hello World!",
        "paragraph": "Lorem ipsum dolor sit amet",
    }


async def _assert_generation_scenario(response: Response):
    text = await response.text()

    assert '<input type="hidden" name="__RequestVerificationToken" value=' in text

    assert response.status == 200

    af_cookie = response.cookies["aftoken"]
    assert af_cookie is not None

    value = af_cookie.value
    assert value is not None

    # the value in the cookie and the value in the input element must be different
    control_value = read_control_value_from_input(text)
    assert value != control_value


async def test_anti_forgery_token_generation(home_model):
    app, render = get_app(False)

    @app.router.get("/")
    async def home(request):
        return render("form_1", home_model, request=request)

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None
    await _assert_generation_scenario(app.response)


async def test_anti_forgery_token_click_jacking_protection(home_model):
    app, render = get_app(False)

    @app.router.get("/")
    async def home(request):
        return render("form_1", home_model, request=request)

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None

    csp = app.response.headers[b"Content-Security-Policy"]
    assert csp == (b"frame-ancestors: 'self';",)

    x_frame_options = app.response.headers[b"X-Frame-Options"]
    assert x_frame_options == (b"SAMEORIGIN",)


async def test_anti_forgery_token_generation_multiple(home_model):
    """
    Verifies that using {% af_input %} doesn't generate multiple values for the same
    web request, and that {% af_token %} returns the token without an HTML fragment.
    """
    app, render = get_app(False)

    @app.router.get("/")
    async def home(request):
        return render("form_2", home_model, request=request)

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    response = app.response
    assert response is not None

    text = await response.text()

    values = list(
        re.findall(r'name="__RequestVerificationToken" value="([^\"]+)"', text)
    )

    assert len(values) == 2

    # all values must be equal
    assert all(value == values[0] for value in values)

    match = re.search(r'{"token": "([^\"]+)"}', text)

    assert match is not None
    value = match.group(1)
    assert value == values[0]

    # the response cookie is only one
    af_cookie = response.cookies["aftoken"]
    assert af_cookie is not None


async def test_anti_forgery_missing_request_context(home_model):
    app, render = get_app(False)
    app.show_error_details = True

    @app.router.get("/")
    async def home():
        return render("form_1", home_model)

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None
    assert app.response.status == 500

    text = await app.response.text()
    assert text is not None
    assert (
        "blacksheep.server.csrf.MissingRequestContextError: The request context is "
        "missing from the render call. Pass the request object to the context of the "
        "template."
    ) in text


async def test_anti_forgery_missing_request_context_hidden(home_model):
    app, render = get_app(False)

    @app.router.get("/")
    async def home():
        return render("form_1", home_model)

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None
    assert app.response.status == 500

    text = await app.response.text()
    assert text == "Internal Server Error"


async def _valid_scenario(app: FakeApplication):
    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None

    text = await app.response.text()

    af_cookie = app.response.cookies["aftoken"]
    assert af_cookie is not None

    # a valid request includes both the control value and the cookie:
    # extract the anti-forgery token, then do POST
    control_value = read_control_value_from_input(text)
    await app(
        get_example_scope(
            "POST",
            "/user",
            extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
            cookies={"aftoken": af_cookie.value},
        ),
        MockReceive(
            [
                write_www_form_urlencoded(
                    {
                        "username": "Charlie Brown",
                        "__RequestVerificationToken": control_value,
                    }
                )
            ]
        ),
        MockSend(),
    )

    response = app.response
    assert response.status == 204


async def test_anti_forgery_token_validation_using_input_1(home_model):
    """
    Tests a valid scenario.
    """
    app, render = get_app(False)

    @app.router.get("/")
    async def home(request):
        return render("form_1", home_model, request=request)

    @app.router.post("/user")
    async def create_username():
        return no_content()

    await _valid_scenario(app)


async def test_anti_forgery_token_validation_using_input_1b(home_model):
    """
    Tests handling of an anomalous situation when the same form contains two elements
    for the verification.
    """
    app, render = get_app(False)

    @app.router.get("/")
    async def home(request):
        return render("form_1", home_model, request=request)

    @app.router.post("/user")
    async def create_username():
        return no_content()

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None

    text = await app.response.text()

    af_cookie = app.response.cookies["aftoken"]
    assert af_cookie is not None

    # a valid request includes both the control value and the cookie:
    # extract the anti-forgery token, then do POST
    control_value = read_control_value_from_input(text).encode()
    await app(
        get_example_scope(
            "POST",
            "/user",
            extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
            cookies={"aftoken": af_cookie.value},
        ),
        MockReceive(
            [
                b"username=Charlie+Brown"
                + b"&__RequestVerificationToken="
                + control_value
                + b"&__RequestVerificationToken="
                + control_value
            ]
        ),
        MockSend(),
    )

    response = app.response
    assert response.status == 204


async def test_anti_forgery_cookie_must_be_http_only(home_model):
    app, render = get_app(False)

    @app.router.get("/")
    async def home(request):
        return render("form_1", home_model, request=request)

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None

    af_cookie = app.response.cookies["aftoken"]
    assert af_cookie is not None
    assert af_cookie.http_only is True


async def test_tokens_reuse_across_requests(home_model):
    """
    When the same client has multiple pages open on the same website, they should use
    by default the same cookie (otherwise opening a new tab breaks the previous tabs
    since the control values in input elements would not be updated!)
    """
    app, render = get_app(False)

    @app.router.get("/")
    async def home(request):
        return render("form_1", home_model, request=request)

    @app.router.post("/user")
    async def create_username():
        return no_content()

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None

    first_cookie = app.response.cookies["aftoken"]
    assert first_cookie is not None

    # now get the same page, but with a request cookie that already contains an
    # anti-forgery token that was generated previously (this could happen in the same
    # page or in another page of the same website)
    await app(
        get_example_scope("GET", "/", cookies={"aftoken": first_cookie.value}),
        MockReceive(),
        MockSend(),
    )

    assert app.response is not None

    # the second response doesn't have a set-cookie header because it's not necessary:
    # the client already has a cookie for anti-forgery validation
    # but we can make a web request with a new control value generated for the second
    # response
    second_cookie = app.response.cookies.get("aftoken")
    assert second_cookie is None

    text = await app.response.text()
    control_value = read_control_value_from_input(text)
    await app(
        get_example_scope(
            "POST",
            "/user",
            extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
            cookies={"aftoken": first_cookie.value},
        ),
        MockReceive(
            [
                write_www_form_urlencoded(
                    {
                        "username": "Charlie Brown",
                        "__RequestVerificationToken": control_value,
                    }
                )
            ]
        ),
        MockSend(),
    )

    response = app.response
    assert response.status == 204


async def test_tokens_reuse_across_requests_invalid_token(home_model):
    """
    Tests an invalid value sent for aftoken cookie.
    """
    app, render = get_app(False)

    @app.router.get("/")
    async def home(request):
        return render("form_1", home_model, request=request)

    @app.router.post("/user")
    async def create_username():
        return no_content()

    await app.start()

    # now get the same page, but with a request cookie that already contains an
    # anti-forgery token that was generated previously (this could happen in the same
    # page or in another page of the same website)
    await app(
        get_example_scope("GET", "/", cookies={"aftoken": "invalid value"}),
        MockReceive(),
        MockSend(),
    )

    assert app.response is not None

    # the second response doesn't have a set-cookie header because it's not necessary:
    # the client already has a cookie for anti-forgery validation
    # but we can make a web request with a new control value generated for the second
    # response
    second_cookie = app.response.cookies.get("aftoken")
    assert second_cookie is not None


async def test_anti_forgery_token_validation_using_input_2(home_model):
    """
    Tests invalid request, missing the value in the cookie.
    """
    app, render = get_app(False)

    @app.router.get("/")
    async def home(request):
        return render("form_1", home_model, request=request)

    @app.router.post("/user")
    async def create_username():
        return no_content()

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None

    text = await app.response.text()

    af_cookie = app.response.cookies["aftoken"]
    assert af_cookie is not None

    # a valid request includes both the control value and the cookie:
    # extract the anti-forgery token, then do POST
    control_value = read_control_value_from_input(text)

    # a request without cookie will fail:
    await app(
        get_example_scope(
            "POST",
            "/user",
            extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
        ),
        MockReceive(
            [
                write_www_form_urlencoded(
                    {
                        "username": "Charlie Brown",
                        "__RequestVerificationToken": control_value,
                    }
                )
            ]
        ),
        MockSend(),
    )

    response = app.response
    assert response.status == 401
    reason = response.headers[b"Reason"]
    assert reason == (b"Missing anti-forgery token cookie",)


async def test_anti_forgery_token_validation_using_input_3(home_model):
    """
    Tests invalid control value, that cannot be deserialized (BadSignature).
    """
    app, render = get_app(False)

    @app.router.get("/")
    async def home(request):
        return render("form_1", home_model, request=request)

    @app.router.post("/user")
    async def create_username():
        return no_content()

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None

    af_cookie = app.response.cookies["aftoken"]
    assert af_cookie is not None

    # a valid request includes both the control value and the cookie:
    # extract the anti-forgery token, then do POST

    # a request with invalid control value will fail:
    await app(
        get_example_scope(
            "POST",
            "/user",
            extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
            cookies={"aftoken": af_cookie.value},
        ),
        MockReceive(
            [
                write_www_form_urlencoded(
                    {
                        "username": "Charlie Brown",
                        "__RequestVerificationToken": "This is wrong",
                    }
                )
            ]
        ),
        MockSend(),
    )

    response = app.response
    assert response.status == 401
    reason = response.headers[b"Reason"]
    assert reason == (b"Invalid anti-forgery token",)


async def test_anti_forgery_token_validation_using_input_4(home_model):
    """
    Tests invalid control value, which was generated for another request.
    """
    app, render = get_app(False)

    @app.router.get("/")
    async def home(request):
        return render("form_1", home_model, request=request)

    @app.router.post("/user")
    async def create_username():
        return no_content()

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None

    text = await app.response.text()
    control_value = read_control_value_from_input(text)
    # a valid request includes both the control value and the cookie:
    # extract the anti-forgery token, then do POST

    # make another web request, which results in obtaining a new unrelated AF token,
    # then use the cookie AF token with the unrelated control value
    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    af_cookie = app.response.cookies["aftoken"]
    assert af_cookie is not None

    # a request with invalid control value will fail:
    await app(
        get_example_scope(
            "POST",
            "/user",
            extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
            cookies={"aftoken": af_cookie.value},
        ),
        MockReceive(
            [
                write_www_form_urlencoded(
                    {
                        "username": "Charlie Brown",
                        "__RequestVerificationToken": control_value,
                    }
                )
            ]
        ),
        MockSend(),
    )

    response = app.response
    assert response.status == 401
    reason = response.headers[b"Reason"]
    assert reason == (b"Invalid anti-forgery token",)


async def test_missing_control_value(home_model):
    """
    Tests missing control value, which was generated for another request.
    """
    app, render = get_app(False)

    @app.router.get("/")
    async def home(request):
        return render("form_1", home_model, request=request)

    @app.router.post("/user")
    async def create_username():
        return no_content()

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None

    af_cookie = app.response.cookies["aftoken"]
    assert af_cookie is not None

    # a request with invalid control value will fail:
    await app(
        get_example_scope(
            "POST",
            "/user",
            extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
            cookies={"aftoken": af_cookie.value},
        ),
        MockReceive([write_www_form_urlencoded({"username": "Charlie Brown"})]),
        MockSend(),
    )

    response = app.response
    assert response.status == 401
    reason = response.headers[b"Reason"]
    assert reason == (b"Missing anti-forgery token control value",)


async def test_anti_forgery_token_validation_using_header(home_model):
    app, render = get_app(False)

    @app.router.get("/")
    async def home(request):
        return render("form_1", home_model, request=request)

    @app.router.post("/user")
    async def create_username():
        return no_content()

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None

    text = await app.response.text()

    af_cookie = app.response.cookies["aftoken"]
    assert af_cookie is not None

    # a valid request includes both the control value and the cookie:
    # extract the anti-forgery token, then do POST
    control_value = read_control_value_from_input(text)
    await app(
        get_example_scope(
            "POST",
            "/user",
            extra_headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "RequestVerificationToken": control_value,
            },
            cookies={"aftoken": af_cookie.value},
        ),
        MockReceive([write_www_form_urlencoded({"username": "Charlie Brown"})]),
        MockSend(),
    )

    response = app.response
    assert response.status == 204


async def test_controller_view_generation(home_model):
    app, _ = get_app(False)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get("/")
        def form_1(self, request):
            return self.view("form_1", model=home_model, request=request)

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None
    await _assert_generation_scenario(app.response)


async def test_controller_async_view_generation(home_model, async_jinja_env):
    app, _ = get_app(True)
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Lorem(Controller):
        @get("/")
        async def form_1(self, request):
            return await self.view_async("form_1", model=home_model, request=request)

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None
    await _assert_generation_scenario(app.response)


async def test_anti_forgery_base_extension_raises_without_handler(home_model):
    assert isinstance(html_settings.renderer, JinjaRenderer)
    env = html_settings.renderer.env

    with pytest.raises(TypeError):
        AntiForgeryBaseExtension(env)

    class Foo(AntiForgeryBaseExtension):
        af_handler = object()  # type: ignore

    instance = Foo(env)
    instance.af_handler = None

    with pytest.raises(TypeError):
        instance.handler


async def test_anti_forgery_ignore_decorator(home_model):
    """
    Tests a valid scenario, using the ignore_anti_forgery decorator.
    """
    app, render = get_app(False)

    @app.router.get("/")
    async def home(request):
        return render("form_1", home_model, request=request)

    @ignore_anti_forgery()
    @app.router.post("/user")
    async def create_username():
        return no_content()

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None

    assert app.response is not None
    af_cookie = app.response.cookies["aftoken"]
    assert af_cookie is not None, "An Anti-Forgery token is still issued for the home."

    await app(
        get_example_scope(
            "POST",
            "/user",
            extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
        ),
        MockReceive([write_www_form_urlencoded({"username": "Charlie Brown"})]),
        MockSend(),
    )

    response = app.response
    assert response.status == 204
