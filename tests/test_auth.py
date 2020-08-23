from typing import Any, Optional

import pytest
from guardpost.authentication import Identity
from guardpost.authorization import AuthorizationContext
from guardpost.common import AuthenticatedRequirement
from pytest import raises

from blacksheep.server.authentication import (AuthenticateChallenge,
                                              AuthenticationHandler)
from blacksheep.server.authorization import (
    AuthorizationWithoutAuthenticationError, Policy, Requirement, auth)

from .test_application import (FakeApplication, MockReceive, MockSend,
                               get_example_scope)


class MockAuthHandler(AuthenticationHandler):

    def __init__(self, identity=None):
        if identity is None:
            identity = Identity({
                'id': '001',
                'name': 'Charlie Brown'
            }, 'JWT')
        self.identity = identity

    async def authenticate(self, context: Any) -> Optional[Identity]:
        context.identity = self.identity
        return context.identity


class MockNotAuthHandler(AuthenticationHandler):

    async def authenticate(self, context: Any) -> Optional[Identity]:
        context.identity = Identity({
            'id': '007',
        })
        # NB: an identity without authentication scheme is treated
        # as anonymous identity
        return context.identity


class AccessTokenCrashingHandler(AuthenticationHandler):

    async def authenticate(self, context: Any) -> Optional[Identity]:
        raise AuthenticateChallenge('Bearer', None, {
            'error': 'Invalid access token',
            'error_description': 'Access token expired'
        })


class AdminRequirement(Requirement):

    def handle(self, context: AuthorizationContext):
        identity = context.identity

        if identity is not None and identity['role'] == 'admin':
            context.succeed(self)


class AdminsPolicy(Policy):

    def __init__(self):
        super().__init__('admin', AdminRequirement())


@pytest.mark.asyncio
async def test_authentication_sets_identity_in_request():
    app = FakeApplication()

    app.use_authentication()\
        .add(MockAuthHandler())

    identity = None

    @app.router.get(b'/')
    async def home(request):
        nonlocal identity
        identity = request.identity
        return None

    app.prepare()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())

    assert app.response.status == 204

    assert identity is not None
    assert identity['id'] == '001'
    assert identity['name'] == 'Charlie Brown'


@pytest.mark.asyncio
async def test_authorization_unauthorized_error():
    app = FakeApplication()

    app.use_authentication()\
        .add(MockAuthHandler())

    app.use_authorization()\
        .add(AdminsPolicy())

    @auth('admin')
    @app.router.get(b'/')
    async def home():
        return None

    app.prepare()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())

    assert app.response.status == 401


@pytest.mark.asyncio
async def test_authorization_policy_success():
    app = FakeApplication()

    admin = Identity({
        'id': '001',
        'name': 'Charlie Brown',
        'role': 'admin'
    }, 'JWT')

    app.use_authentication()\
        .add(MockAuthHandler(admin))

    app.use_authorization()\
        .add(AdminsPolicy())

    @auth('admin')
    @app.router.get(b'/')
    async def home():
        return None

    app.prepare()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())

    assert app.response.status == 204


@pytest.mark.asyncio
async def test_authorization_default_allows_anonymous():
    app = FakeApplication()

    app.use_authentication()\
        .add(MockAuthHandler())

    app.use_authorization()\
        .add(AdminsPolicy())

    @app.router.get(b'/')
    async def home():
        return None

    app.prepare()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())

    assert app.response.status == 204


@pytest.mark.asyncio
async def test_authorization_supports_default_require_authenticated():
    app = FakeApplication()

    app.use_authentication()\
        .add(MockNotAuthHandler())

    app.use_authorization()\
        .add(AdminsPolicy())\
        .default_policy += AuthenticatedRequirement()

    @app.router.get(b'/')
    async def home():
        return None

    app.prepare()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())

    assert app.response.status == 401


@pytest.mark.asyncio
async def test_authentication_challenge_response():
    app = FakeApplication()

    app.use_authentication()\
        .add(AccessTokenCrashingHandler())

    app.use_authorization()\
        .add(AdminsPolicy())\
        .default_policy += AuthenticatedRequirement()

    @app.router.get(b'/')
    async def home():
        return None

    app.prepare()
    await app(get_example_scope('GET', '/'), MockReceive(), MockSend())

    assert app.response.status == 401
    header = app.response.get_single_header(b'WWW-Authenticate')

    assert header is not None
    assert header == (b'Bearer, error="Invalid access token", '
                      b'error_description="Access token expired"')


@pytest.mark.asyncio
async def test_authorization_strategy_without_authentication_raises():
    app = FakeApplication()

    app.use_authorization()

    with raises(AuthorizationWithoutAuthenticationError):
        app.prepare()


@pytest.mark.parametrize('scheme,realm,parameters,expected_value', [

    ['Basic', None, None, b'Basic'],
    ['Bearer', 'Mushrooms Kingdom', None, b'Bearer realm="Mushrooms Kingdom"'],
    ['Bearer', 'Mushrooms Kingdom', {'title': 'Something',
                                     'error': 'Invalid access token',
                                     'error_description': 'access token expired'},
     b'Bearer realm="Mushrooms Kingdom", '
     b'title="Something", '
     b'error="Invalid access token", '
     b'error_description="access token expired"']
])
def test_authentication_challenge_error(scheme, realm, parameters, expected_value):
    error = AuthenticateChallenge(scheme, realm, parameters)

    header = error.get_header()
    assert header[0] == b'WWW-Authenticate'
    assert header[1] == expected_value
