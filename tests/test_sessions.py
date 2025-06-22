import time

import pytest

from blacksheep.cookies import parse_cookie
from blacksheep.messages import Request
from blacksheep.server.responses import text
from blacksheep.sessions import Session
from blacksheep.sessions.cookies import CookieSessionStore
from blacksheep.sessions.json import JSONSerializer
from blacksheep.sessions.memory import InMemorySessionStore
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend


def test_friendly_exception_for_request_without_session():
    request = Request("GET", b"/", None)

    with pytest.raises(TypeError):
        request.session


def test_session_base_methods():
    session = Session()

    assert "foo" not in session

    session["foo"] = "lorem ipsum"

    assert "foo" in session
    assert session["foo"] == "lorem ipsum"

    del session["foo"]

    assert "foo" not in session

    session.set("foo", "lorem ipsum")
    assert session.get("foo") == "lorem ipsum"

    assert session.get("ufo", ...) is ...

    session.update({"a": 1, "b": 2, "c": 3})

    assert session["a"] == 1
    assert session["b"] == 2
    assert session["c"] == 3


@pytest.mark.parametrize(
    "values,expected_len",
    [
        [
            {},
            0,
        ],
        [
            {
                "a": 1,
                "b": 2,
            },
            2,
        ],
        [
            {
                "a": 1,
                "b": 2,
                "c": 3,
            },
            3,
        ],
        [{"a": 1, "b": 2, "c": 3, "d": 4}, 4],
    ],
)
def test_session_length(values, expected_len):
    session = Session(values)
    assert len(session) == expected_len


def test_session_clear():
    session = Session({"a": 1, "b": 2, "c": 3, "d": 4})

    session.clear()
    assert session.modified
    assert len(session) == 0


def test_session_to_dict():
    value = {"a": 1, "b": 2, "c": 3, "d": 4}
    session = Session(value)

    assert session.to_dict() == value
    assert session.to_dict() is not value


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"a": 1},
        {"a": 1, "b": 2},
        {"a": 1, "b": 2, "c": 3},
        {"a": 1, "b": 2, "c": 3, "d": 4},
    ],
)
def test_session_equality(values):
    session = Session(values)

    assert session == session
    assert session == Session(values)
    assert session == values

    values["x"] = True

    assert session != Session(values)
    assert session != values


def test_session_inequality():
    session = Session()
    assert (session == []) is False
    assert (session == "") is False


def test_session_modified():
    session = Session()

    assert session.modified is False

    session["foo"] = "lorem ipsum"

    assert session.modified is True

    session = Session({"foo": "lorem ipsum"})

    assert session.modified is False

    # any set item marks the session as modified,
    # it doesn't matter if the end values are the same
    session["foo"] = "lorem ipsum"

    assert session.modified is True


def test_session_modified_set():
    session = Session()

    assert session.modified is False

    session.set("foo", "lorem ipsum")

    assert session.modified is True


def test_session_modified_del():
    session = Session({"foo": "lorem ipsum"})

    assert session.modified is False

    del session["foo"]

    assert session.modified is True


def test_session_key_error():
    session = Session()

    with pytest.raises(KeyError):
        session["foo"]


@pytest.mark.parametrize(
    "value,session",
    [
        ["{}", Session()],
        ['{"lorem":"ipsum"}', Session({"lorem": "ipsum"})],
        ['{"lorem":"ipsum ✨"}', Session({"lorem": "ipsum ✨"})],
    ],
)
def test_session_json_serializer(value, session):
    serializer = JSONSerializer()

    assert serializer.write(session) == value
    assert serializer.read(value) == session


async def test_session_middleware_basics(app):
    app.use_sessions("LOREM_IPSUM")

    @app.router.get("/")
    def home(request: Request):
        session = request.session

        assert isinstance(session, Session)
        session["foo"] = "Some value"

        return text("Hello, World")

    @app.router.get("/second")
    def second(request: Request):
        session = request.session

        assert "foo" in session
        assert session["foo"] == "Some value"

        return text("Hello, World")

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200

    session_set_cookie = response.headers.get_single(b"Set-Cookie")
    assert session_set_cookie is not None

    cookie = parse_cookie(session_set_cookie)

    await app(
        get_example_scope("GET", "/second", {"cookie": f"session={cookie.value}"}),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200

    session_set_cookie = response.headers.get_first(b"Set-Cookie")
    assert session_set_cookie is None


async def test_session_middleware_use_method(app):
    app.use_sessions("LOREM_IPSUM")

    @app.router.get("/")
    def home(request: Request):
        session = request.session

        assert isinstance(session, Session)
        session["foo"] = "Some value"

        return text("Hello, World")

    @app.router.get("/second")
    def second(request: Request):
        session = request.session

        assert "foo" in session
        assert session["foo"] == "Some value"

        return text("Hello, World")

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200

    session_set_cookie = response.headers.get_single(b"Set-Cookie")
    assert session_set_cookie is not None

    cookie = parse_cookie(session_set_cookie)

    await app(
        get_example_scope("GET", "/second", {"cookie": f"session={cookie.value}"}),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200

    session_set_cookie = response.headers.get_first(b"Set-Cookie")
    assert session_set_cookie is None


async def test_session_middleware_in_memory_store(app):
    """
    Test the other way to configure sessions, using a specific SessionStore.
    """
    app.use_sessions(InMemorySessionStore())

    @app.router.get("/")
    def home(request: Request):
        session = request.session

        assert isinstance(session, Session)
        session["foo"] = "Some value"

        return text("Hello, World")

    @app.router.get("/second")
    def second(request: Request):
        session = request.session

        assert "foo" in session
        assert session["foo"] == "Some value"

        return text("Hello, World")

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200

    session_set_cookie = response.headers.get_single(b"Set-Cookie")
    assert session_set_cookie is not None

    cookie = parse_cookie(session_set_cookie)

    await app(
        get_example_scope("GET", "/second", {"cookie": f"session={cookie.value}"}),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200

    session_set_cookie = response.headers.get_first(b"Set-Cookie")
    assert session_set_cookie is None


async def test_session_middleware_handling_of_invalid_signature(app):
    app.use_sessions("LOREM_IPSUM")

    @app.router.get("/")
    def home(request: Request):
        session = request.session

        assert isinstance(session, Session)
        assert len(session) == 0
        assert "user_id" not in session

        return text("Hello, World")

    await app.start()

    # arrange invalid session cookie
    impostor_middleware = CookieSessionStore("DOLOR_SIT_AMET")

    forged_cookie = impostor_middleware._write_session(Session({"user_id": "hahaha"}))

    await app(
        get_example_scope("GET", "/", {"cookie": f"session={forged_cookie}"}),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200


async def test_session_middleware_handling_of_expired_signature(app):
    app.use_sessions("LOREM_IPSUM", session_max_age=1)

    @app.router.get("/")
    def home(request: Request):
        session = request.session

        assert isinstance(session, Session)
        session["foo"] = "Some value"

        return text("Hello, World")

    @app.router.get("/second")
    def second(request: Request):
        session = request.session

        assert "foo" not in session

        return text("Hello, World")

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200

    session_set_cookie = response.headers.get_single(b"Set-Cookie")
    assert session_set_cookie is not None

    cookie = parse_cookie(session_set_cookie)

    time.sleep(2)

    await app(
        get_example_scope("GET", "/second", {"cookie": f"session={cookie.value}"}),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200

    session_set_cookie = response.headers.get_first(b"Set-Cookie")
    assert session_set_cookie is None


def test_exception_for_invalid_max_age():
    with pytest.raises(ValueError):
        CookieSessionStore("example", session_max_age=0)

    with pytest.raises(ValueError):
        CookieSessionStore("example", session_max_age=-10)
