import pytest
from blacksheep.server.cors import CORSPolicy


def test_cors_policy():
    policy = CORSPolicy(
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization"],
        allow_origins=["http://localhost:44555"],
    )
    assert policy.allow_methods == {"GET", "POST", "DELETE"}
    assert policy.allow_headers == {"authorization"}
    assert policy.allow_origins == {"http://localhost:44555"}


def test_cors_policy_setters_strings():
    policy = CORSPolicy()

    policy.allow_methods = "get delete"
    assert policy.allow_methods == {"GET", "DELETE"}

    policy.allow_methods = "GET POST PATCH"
    assert policy.allow_methods == {"GET", "POST", "PATCH"}

    policy.allow_methods = "GET, POST, PATCH"
    assert policy.allow_methods == {"GET", "POST", "PATCH"}

    policy.allow_methods = "GET,POST,PATCH"
    assert policy.allow_methods == {"GET", "POST", "PATCH"}

    policy.allow_methods = "GET;POST;PATCH"
    assert policy.allow_methods == {"GET", "POST", "PATCH"}

    for value in {"X-Foo Authorization", "X-Foo, Authorization", "X-Foo,Authorization"}:
        policy.allow_headers = value
        assert policy.allow_headers == {"x-foo", "authorization"}

    policy.allow_origins = "http://Example.com https://Bezkitu.ORG"
    assert policy.allow_origins == {"http://example.com", "https://bezkitu.org"}


def test_cors_policy_setters_force_case():
    policy = CORSPolicy()

    policy.allow_methods = ["get", "delete"]
    assert policy.allow_methods == {"GET", "DELETE"}

    policy.allow_headers = ["X-Foo", "Authorization"]
    assert policy.allow_headers == {"x-foo", "authorization"}

    policy.allow_origins = ["http://Example.com", "https://Bezkitu.ORG"]
    assert policy.allow_origins == {"http://example.com", "https://bezkitu.org"}


def test_cors_policy_allow_all_methods():
    policy = CORSPolicy()

    assert policy.allow_headers == set()
    policy.allow_any_header()
    assert policy.allow_headers == {"*"}

    assert policy.allow_methods == set()
    policy.allow_any_method()
    assert policy.allow_methods == {"*"}

    assert policy.allow_origins == set()
    policy.allow_any_origin()
    assert policy.allow_origins == {"*"}


def test_cors_policy_raises_for_negative_max_age():
    with pytest.raises(ValueError):
        CORSPolicy(max_age=-1)

    policy = CORSPolicy()
    with pytest.raises(ValueError):
        policy.max_age = -5
