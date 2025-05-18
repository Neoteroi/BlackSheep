import pytest

from blacksheep.url import URL, InvalidURL, join_prefix


def test_empty_url():
    with pytest.raises(InvalidURL):
        URL(b"")


def test_absolute_url():
    url = URL(b"https://robertoprevato.github.io?foo=power&hello=world")

    # The following assertion looks weird because of the behavior of different libraries
    # as BlackSheep relies on other libraries to do the actual parsing:
    # YARL gives path "/", httptools None, urlli urlparse ""
    #
    # YARL in my opinion gives wrong results for path and port. Gives "443" which is
    # the default for the scheme even though no port is specified in the URL (I would
    # expect it to give 443 only if explicitly set such as in domain:443); and for the
    # path it gives "/" when no path is specified (domain/ and domain are not exactly
    # the same).
    assert url.path in {b"", b"/", None}
    assert url.schema == b"https"
    assert url.host == b"robertoprevato.github.io"
    assert url.port in {443, 0}
    assert url.query == b"foo=power&hello=world"
    assert url.fragment is None
    assert url.is_absolute is True


def test_relative_url():
    url = URL(b"/api/cat/001?foo=power&hello=world")

    assert url.path == b"/api/cat/001"
    assert url.schema is None
    assert url.host is None
    assert url.port == 0
    assert url.query == b"foo=power&hello=world"
    assert url.fragment is None
    assert url.is_absolute is False


def test_equality():
    assert URL(b"/") == URL(b"/")
    assert URL(b"/api/cats") == URL(b"/api/cats")
    assert URL(b"/api/cats") != URL(b"/api/cat/001")


def test_concatenation():
    assert URL(b"/") + URL(b"/") == URL(b"/")
    assert URL(b"https://world-cats.eu") + URL(b"/api/cats") == URL(
        b"https://world-cats.eu/api/cats"
    )
    assert URL(b"https://world-cats.eu/") + URL(b"/api/cats") == URL(
        b"https://world-cats.eu/api/cats"
    )


def test_cannot_concatenate_one_url_first_with_query_or_path():
    with pytest.raises(ValueError):
        URL(b"https://world-cats.eu?hello=world") + URL(b"/api/cats")

    with pytest.raises(ValueError):
        URL(b"http://world-cats.eu/#/about") + URL(b"/api/cats")


def test_cannot_concatenate_absolute_urls():
    with pytest.raises(ValueError):
        URL(b"https://world-cats.eu") + URL(b"https://hello-world")

    with pytest.raises(ValueError):
        URL(b"http://world-cats.eu") + URL(b"http://hello-world")


@pytest.mark.parametrize(
    "value,expected_base_url",
    [
        [
            b"https://robertoprevato.github.io/api/v1/cats",
            b"https://robertoprevato.github.io",
        ],
        [
            b"https://robertoprevato.github.io:44555/api/v1/cats",
            b"https://robertoprevato.github.io:44555",
        ],
        [
            b"https://robertoprevato.github.io/api/v1/cats?lorem=ipsum",
            b"https://robertoprevato.github.io",
        ],
        [
            b"https://robertoprevato.github.io?lorem=ipsum",
            b"https://robertoprevato.github.io",
        ],
        [
            b"http://robertoprevato.github.io/api/v1/cats",
            b"http://robertoprevato.github.io",
        ],
        [
            b"http://robertoprevato.github.io:44555/api/v1/cats",
            b"http://robertoprevato.github.io:44555",
        ],
        [
            b"http://robertoprevato.github.io/api/v1/cats?lorem=ipsum",
            b"http://robertoprevato.github.io",
        ],
        [
            b"http://robertoprevato.github.io?lorem=ipsum",
            b"http://robertoprevato.github.io",
        ],
    ],
)
def test_base_url(value, expected_base_url):
    url = URL(value)
    base_url = url.base_url()
    assert expected_base_url == base_url.value


def test_raises_for_invalid_scheme():
    with pytest.raises(InvalidURL):
        URL(b"file://D:/a/b/c")


@pytest.mark.parametrize(
    "prefix,value,expected_result",
    [
        ("/", "/", "/"),
        ("", "/cats", "/cats"),
        ("/", "/cats", "/cats"),
        ("/", "/api/cats", "/api/cats"),
        ("/api", "/cats", "/api/cats"),
        ("/api", "cats", "/api/cats"),
        ("/api/", "/cats", "/api/cats"),
        ("/api/", "cats", "/api/cats"),
        ("/api", "/cats/", "/api/cats/"),
        ("/api", "cats/", "/api/cats/"),
        ("/api/", "/cats/", "/api/cats/"),
        ("/api/", "cats/", "/api/cats/"),
    ],
)
def test_join_prefix(prefix, value, expected_result):
    assert join_prefix(prefix, value) == expected_result
