import pytest
from blacksheep.url import URL


def test_empty_url():
    url = URL(b'')

    assert url.path is None
    assert url.schema is None
    assert url.host is None
    assert url.port is None
    assert url.query is None
    assert url.fragment is None
    assert url.userinfo is None
    assert url.is_absolute is False


def test_absolute_url():
    url = URL(b'https://hello-world.eu?foo=power&hello=world')

    assert url.path is None
    assert url.schema == b'https'
    assert url.host == b'hello-world.eu'
    assert url.port is None
    assert url.query == b'foo=power&hello=world'
    assert url.fragment is None
    assert url.userinfo is None
    assert url.is_absolute is True


def test_relative_url():
    url = URL(b'/api/cat/001?foo=power&hello=world')

    assert url.path == b'/api/cat/001'
    assert url.schema is None
    assert url.host is None
    assert url.port is None
    assert url.query == b'foo=power&hello=world'
    assert url.fragment is None
    assert url.userinfo is None
    assert url.is_absolute is False


def test_relative_url_friendly_constructor():
    url = URL(b'api/cat/001?foo=power&hello=world')

    assert url.path == b'/api/cat/001'
    assert url.schema is None
    assert url.host is None
    assert url.port is None
    assert url.query == b'foo=power&hello=world'
    assert url.fragment is None
    assert url.userinfo is None
    assert url.is_absolute is False


def test_equality():
    assert URL(b'') == URL(b'')
    assert URL(b'/api/cats') == URL(b'/api/cats')
    assert URL(b'/api/cats') != URL(b'/api/cat/001')


def test_concatenation():
    assert URL(b'') + URL(b'') == URL(b'')
    assert URL(b'https://world-cats.eu') + URL(b'/api/cats') == URL(b'https://world-cats.eu/api/cats')
    assert URL(b'https://world-cats.eu/') + URL(b'/api/cats') == URL(b'https://world-cats.eu/api/cats')
    assert URL(b'https://world-cats.eu') + URL(b'api/cats') == URL(b'https://world-cats.eu/api/cats')


def test_cannot_concatenate_one_url_first_with_query_or_path():
    with pytest.raises(ValueError):
        URL(b'https://world-cats.eu?hello=world') + URL(b'/api/cats')

    with pytest.raises(ValueError):
        URL(b'http://world-cats.eu/#/about') + URL(b'/api/cats')


def test_cannot_concatenate_absolute_urls():
    with pytest.raises(ValueError):
        URL(b'https://world-cats.eu') + URL(b'https://hello-world')

    with pytest.raises(ValueError):
        URL(b'http://world-cats.eu') + URL(b'http://hello-world')
