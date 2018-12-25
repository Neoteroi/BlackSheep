import pytest
from blacksheep import HttpRequest, HttpResponse, HttpHeaders, HttpHeader, TextContent, HtmlContent
from blacksheep.client import ClientSession, CircularRedirectError, MaximumRedirectsExceededError
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
@pytest.mark.parametrize('responses,expected_status,expected_location', get_scenarios(lambda status: [
    [
        HttpResponse(status, HttpHeaders([HttpHeader(b'Location',
                                                     b'urn:oasis:names:specification:docbook:dtd:xml:4.1.2')])),
        HttpResponse(200, HttpHeaders(), TextContent('Hello, World!'))
    ], status, b'urn:oasis:names:specification:docbook:dtd:xml:4.1.2'
]) + get_scenarios(lambda status: [
    [
        HttpResponse(status,
                     HttpHeaders([HttpHeader(b'Location', b'msalf84227e26-9a47-4c00-a92c-1b1bad8225cc://auth')])),
        HttpResponse(200, HttpHeaders(), TextContent('Hello, World!'))
    ], status, b'msalf84227e26-9a47-4c00-a92c-1b1bad8225cc://auth'
]))
async def test_non_url_redirect(responses, expected_status, expected_location, pools_factory):

    async with ClientSession(url=b'http://localhost:8080', pools=pools_factory(responses)) as client:
        response = await client.get(b'/')

        assert response is not None
        assert response.status == expected_status

        location_header = response.headers.get_single(b'Location')
        assert location_header.value == expected_location


@pytest.mark.asyncio
@pytest.mark.parametrize('responses,expected_response_body', get_scenarios(lambda status: [
    [
        HttpResponse(status, HttpHeaders([HttpHeader(b'Location', b'/a')])),
        HttpResponse(status, HttpHeaders([HttpHeader(b'Location', b'/b')])),
        HttpResponse(200, HttpHeaders(), TextContent('Hello, World!'))
    ], 'Hello, World!'
]) + get_scenarios(lambda status: [
    [
        HttpResponse(status, HttpHeaders([HttpHeader(b'Location', b'/a')])),
        HttpResponse(200, HttpHeaders(), HtmlContent('<h1>Hello, World!</h1>'))
    ], '<h1>Hello, World!</h1>'
]))
async def test_good_redirect(responses, expected_response_body, pools_factory):

    async with ClientSession(url=b'http://localhost:8080', pools=pools_factory(responses)) as client:
        response = await client.get(b'/')

        assert response is not None
        assert response.status == 200

        content = await response.text()
        assert content == expected_response_body


@pytest.mark.asyncio
@pytest.mark.parametrize('responses,expected_location', [
    [
        [
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/a')])),
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/b')])),
            HttpResponse(200, HttpHeaders(), TextContent('Hello, World!'))
        ], b'/a'
    ]
])
async def test_not_follow_redirect(responses, expected_location, pools_factory):

    async with ClientSession(url=b'http://localhost:8080',
                             pools=pools_factory(responses),
                             follow_redirects=False) as client:
        response = await client.get(b'/')

        assert response.status == 302

        location = response.headers[b'location']
        assert location
        assert location[0].value == expected_location


@pytest.mark.asyncio
@pytest.mark.parametrize('responses,maximum_redirects', [
    [
        [
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/a')])),
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/b')])),
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/c')])),
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/d')])),
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/e')]))
        ], 5
    ],
    [
        [
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/a')])),
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/b')])),
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/c')]))
        ], 2
    ],
    [
        [
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/a')])),
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/b')]))
        ], 1
    ]
])
async def test_maximum_number_of_redirects_detection(responses, maximum_redirects, pools_factory):

    async with ClientSession(url=b'http://localhost:8080', pools=pools_factory(responses)) as client:
        client.maximum_redirects = maximum_redirects

        with pytest.raises(MaximumRedirectsExceededError):
            await client.get(b'/')


@pytest.mark.asyncio
@pytest.mark.parametrize('responses,expected_error_message', [
    [
        [
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/hello-world')])),
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/circular-dependency')])),
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/')]))
        ],
        'Circular redirects detected. Requests path was: '
        '(http://localhost:8080/ '
        '--> http://localhost:8080/hello-world '
        '--> http://localhost:8080/circular-dependency '
        '--> http://localhost:8080/).'
    ],
    [
        [
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'https://identity-provider.some/login')])),
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'http://localhost:8080/welcome')])),
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'https://identity-provider.some/login')]))
        ],
        'Circular redirects detected. Requests path was: '
        '(http://localhost:8080/ '
        '--> https://identity-provider.some/login '
        '--> http://localhost:8080/welcome '
        '--> https://identity-provider.some/login).'
    ],
    [
        [
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/a')])),
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/a')]))
        ],
        'Circular redirects detected. Requests path was: '
        '(http://localhost:8080/ '
        '--> http://localhost:8080/a '
        '--> http://localhost:8080/a).'
    ],
    [
        [
            HttpResponse(302, HttpHeaders([HttpHeader(b'Location', b'/')]))
        ],
        'Circular redirects detected. Requests path was: '
        '(http://localhost:8080/ '
        '--> http://localhost:8080/).'
    ]
])
async def test_circular_redirect_detection(responses, expected_error_message, pools_factory):

    async with ClientSession(url=b'http://localhost:8080', pools=pools_factory(responses)) as client:

        with pytest.raises(CircularRedirectError) as error:
            await client.get(b'/')

        assert str(error.value) == expected_error_message
