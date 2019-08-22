import json
import uvicorn
from base64 import urlsafe_b64decode
from blacksheep import Response, TextContent
from blacksheep.server import Application
from itests.utils import CrashTest
from blacksheep.server.authentication import AuthenticationHandler
from blacksheep.server.authorization import auth, Policy, Requirement
from guardpost.authentication import Identity
from guardpost.authorization import AuthorizationContext
from guardpost.common import AuthenticatedRequirement


app_two = Application()


class HandledException(Exception):

    def __init__(self):
        super().__init__('Example exception')


async def handle_test_exception(app, request, http_exception):
    return Response(200, content=TextContent(f'Fake exception, to test handlers'))


app_two.exceptions_handlers[HandledException] = handle_test_exception


class AdminRequirement(Requirement):

    def handle(self, context: AuthorizationContext):
        identity = context.identity

        if identity is not None and identity.claims.get('role') == 'admin':
            context.succeed(self)


class AdminsPolicy(Policy):

    def __init__(self):
        super().__init__('admin', AdminRequirement())


class MockAuthHandler(AuthenticationHandler):

    def __init__(self):
        pass

    async def authenticate(self, context):
        header_value = context.get_first_header(b'Authorization')
        if header_value:
            data = json.loads(urlsafe_b64decode(header_value).decode('utf8'))
            context.identity = Identity(data, 'FAKE')
        else:
            context.identity = None
        return context.identity


app_two.use_authentication().add(MockAuthHandler())


app_two.use_authorization()\
    .add(AdminsPolicy())\
    .add(Policy('authenticated', AuthenticatedRequirement()))


@auth('admin')
@app_two.router.get('/only-for-admins')
async def only_for_admins():
    return None


@auth('authenticated')
@app_two.router.get('/only-for-authenticated-users')
async def only_for_authenticated_users():
    return None


@app_two.route('/crash')
async def crash():
    raise CrashTest()


@app_two.route('/handled-crash')
async def crash():
    raise HandledException()


if __name__ == '__main__':
    uvicorn.run(app_two, host='127.0.0.1', port=44566, log_level="debug")
