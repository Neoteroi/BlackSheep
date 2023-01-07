import http

import pytest

from blacksheep import URL, HTMLContent, Response, TextContent
from blacksheep.client import (
    CircularRedirectError,
    ClientSession,
    MaximumRedirectsExceededError,
)
from blacksheep.client.exceptions import MissingLocationForRedirect
from blacksheep.client.session import RedirectsCache

from . import FakePools


@pytest.fixture
def pools_factory():
    def get_pools(fake_responses):
        return FakePools(fake_responses)

    return get_pools


def get_scenarios(fn):
    args = []
    for status in {301, 302, 303, 307, 308}:
        args.append(fn(status))
    return args


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "responses,expected_status,expected_location",
    get_scenarios(
        lambda status: [
            [
                Response(
                    status,
                    [
                        (
                            b"Location",
                            b"urn:oasis:names:specification:docbook:dtd:xml:4.1.2",
                        )
                    ],
                ),
                Response(200, None, TextContent("Hello, World!")),
            ],
            status,
            b"urn:oasis:names:specification:docbook:dtd:xml:4.1.2",
        ]
    )
    + get_scenarios(
        lambda status: [
            [
                Response(
                    status,
                    [
                        (
                            b"Location",
                            b"msalf84227e26-9a47-4c00-a92c-1b1bad8225cc://auth",
                        )
                    ],
                ),
                Response(200, None, TextContent("Hello, World!")),
            ],
            status,
            b"msalf84227e26-9a47-4c00-a92c-1b1bad8225cc://auth",
        ]
    ),
)
async def test_non_url_redirect(
    responses, expected_status, expected_location, pools_factory
):

    async with ClientSession(
        base_url=b"http://localhost:8080", pools=pools_factory(responses)
    ) as client:
        response = await client.get(b"/")

        assert response is not None
        assert response.status == expected_status

        location_header = response.headers.get_single(b"Location")
        assert location_header == expected_location


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "responses,expected_response_body",
    get_scenarios(
        lambda status: [
            [
                Response(status, [(b"Location", b"/a")]),
                Response(status, [(b"Location", b"/b")]),
                Response(200, None, TextContent("Hello, World!")),
            ],
            "Hello, World!",
        ]
    )
    + get_scenarios(
        lambda status: [
            [
                Response(status, [(b"Location", b"/a")]),
                Response(200, None, HTMLContent("<h1>Hello, World!</h1>")),
            ],
            "<h1>Hello, World!</h1>",
        ]
    ),
)
async def test_good_redirect(responses, expected_response_body, pools_factory):

    async with ClientSession(
        base_url=b"http://localhost:8080", pools=pools_factory(responses)
    ) as client:
        response = await client.get(b"/")

        assert response is not None
        assert response.status == 200

        content = await response.text()
        assert content == expected_response_body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "responses,expected_location",
    [
        [
            [
                Response(302, [(b"Location", b"/a")]),
                Response(302, [(b"Location", b"/b")]),
                Response(200, None, TextContent("Hello, World!")),
            ],
            b"/a",
        ]
    ],
)
async def test_not_follow_redirect(responses, expected_location, pools_factory):

    async with ClientSession(
        base_url=b"http://localhost:8080",
        pools=pools_factory(responses),
        follow_redirects=False,
    ) as client:
        response = await client.get(b"/")

        assert response.status == 302

        location = response.headers[b"location"]
        assert location
        assert location[0] == expected_location


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "responses,maximum_redirects",
    [
        [
            [
                Response(302, [(b"Location", b"/a")]),
                Response(302, [(b"Location", b"/b")]),
                Response(302, [(b"Location", b"/c")]),
                Response(302, [(b"Location", b"/d")]),
                Response(302, [(b"Location", b"/e")]),
            ],
            5,
        ],
        [
            [
                Response(302, [(b"Location", b"/a")]),
                Response(302, [(b"Location", b"/b")]),
                Response(302, [(b"Location", b"/c")]),
            ],
            2,
        ],
        [
            [
                Response(302, [(b"Location", b"/a")]),
                Response(302, [(b"Location", b"/b")]),
            ],
            1,
        ],
    ],
)
async def test_maximum_number_of_redirects_detection(
    responses, maximum_redirects, pools_factory
):

    async with ClientSession(
        base_url=b"http://localhost:8080", pools=pools_factory(responses)
    ) as client:
        client.maximum_redirects = maximum_redirects

        with pytest.raises(MaximumRedirectsExceededError):
            await client.get(b"/")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "responses,expected_error_message",
    [
        [
            [
                Response(302, [(b"Location", b"/hello-world")]),
                Response(302, [(b"Location", b"/circular-dependency")]),
                Response(302, [(b"Location", b"/")]),
            ],
            "Circular redirects detected. Requests path was: "
            "(http://localhost:8080/ "
            "--> http://localhost:8080/hello-world "
            "--> http://localhost:8080/circular-dependency "
            "--> http://localhost:8080/).",
        ],
        [
            [
                Response(302, [(b"Location", b"https://identity-provider.some/login")]),
                Response(302, [(b"Location", b"http://localhost:8080/welcome")]),
                Response(302, [(b"Location", b"https://identity-provider.some/login")]),
            ],
            "Circular redirects detected. Requests path was: "
            "(http://localhost:8080/ "
            "--> https://identity-provider.some/login "
            "--> http://localhost:8080/welcome "
            "--> https://identity-provider.some/login).",
        ],
        [
            [
                Response(302, [(b"Location", b"/a")]),
                Response(302, [(b"Location", b"/a")]),
            ],
            "Circular redirects detected. Requests path was: "
            "(http://localhost:8080/ "
            "--> http://localhost:8080/a "
            "--> http://localhost:8080/a).",
        ],
        [
            [Response(302, [(b"Location", b"/")])],
            "Circular redirects detected. Requests path was: "
            "(http://localhost:8080/ "
            "--> http://localhost:8080/).",
        ],
    ],
)
async def test_circular_redirect_detection(
    responses, expected_error_message, pools_factory
):

    async with ClientSession(
        base_url=b"http://localhost:8080", pools=pools_factory(responses)
    ) as client:

        with pytest.raises(CircularRedirectError) as error:
            await client.get(b"/")

        assert str(error.value) == expected_error_message


def test_session_raises_for_redirect_without_location():
    """
    If a server returns a redirect status without location response header,
    the client raises an exception.
    """

    with pytest.raises(MissingLocationForRedirect):
        ClientSession.extract_redirect_location(Response(http.HTTPStatus.FOUND.value))


@pytest.mark.parametrize(
    "source,destination",
    [
        (b"https://foo.org", b"https://somewhere-else.org"),
        (b"/something", b"https://somewhere-else.org"),
        (b"/", b"/foo"),
    ],
)
def test_redirects_cache(source, destination):
    cache = RedirectsCache()
    cache[source] = URL(destination)
    assert cache[source] == URL(destination)


def test_redirects_cache_missing():
    cache = RedirectsCache()
    assert cache[b"/foo"] is None


@pytest.mark.asyncio
async def test_use_standard_redirect():
    async with ClientSession(base_url=b"http://localhost:8080") as client:
        assert client.non_standard_handling_of_301_302_redirect_method is True
        client.use_standard_redirect()
        assert client.non_standard_handling_of_301_302_redirect_method is False
