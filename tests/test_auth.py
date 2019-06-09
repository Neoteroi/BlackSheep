import pytest
from guardpost.authentication import Identity
from typing import Any, Optional
from guardpost.authorization import AuthorizationContext, BaseRequirement
from .test_application import FakeApplication, get_new_connection_handler
from blacksheep.server.authentication import AuthenticationHandler
from blacksheep.server.authorization import auth, Policy, Requirement
from guardpost.common import AuthenticatedRequirement


class MockAuthHandler(AuthenticationHandler):

    def __init__(self, identity = None):
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
        })  # NB: an identity without authentication scheme is treated as anonymous identity
        return context.identity


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

    handler = get_new_connection_handler(app)

    handler.data_received(b'GET / HTTP/1.1\r\n\r\n')

    await app.response_done.wait()

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

    handler = get_new_connection_handler(app)

    handler.data_received(b'GET / HTTP/1.1\r\n\r\n')

    await app.response_done.wait()

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

    handler = get_new_connection_handler(app)

    handler.data_received(b'GET / HTTP/1.1\r\n\r\n')

    await app.response_done.wait()

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

    handler = get_new_connection_handler(app)

    handler.data_received(b'GET / HTTP/1.1\r\n\r\n')

    await app.response_done.wait()

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

    handler = get_new_connection_handler(app)

    handler.data_received(b'GET / HTTP/1.1\r\n\r\n')

    await app.response_done.wait()

    assert app.response.status == 401
