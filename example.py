from datetime import datetime
from typing import Any, Optional

from guardpost.authentication import Identity
from blacksheep import Request
from blacksheep.server import Application
from blacksheep.server.responses import text
from blacksheep.server.authentication import AuthenticationStrategy, AuthenticationHandler
from blacksheep.server.authorization import AuthorizationStrategy, auth, allow_anonymous


app = Application(debug=True)


# TODO: JWT Bearer Token, in a library guardpost-jwt (dep. PyJWT + abstract class to obtain JWKS)
class MyAuthenticationHandler(AuthenticationHandler):

    async def authenticate(self, context: Request) -> Optional[Identity]:
        context.identity = None#Identity({
            #'name': 'Example'
        #}, 'MyAuthentication')
        #return context.identity


async def middleware_one(request, handler):
    print('..1')
    return await handler(request)


async def middleware_two(request, handler):
    print('..2')
    return await handler(request)


async def middleware_three(request, handler):
    print('..3')
    return await handler(request)


app.use_authentication(AuthenticationStrategy(MyAuthenticationHandler()))
app.use_authorization(AuthorizationStrategy(lambda request: request.identity))
app.middlewares.append(middleware_one)
app.middlewares.append(middleware_two)
app.middlewares.append(middleware_three)


@auth()
@app.route('/')
async def home(request):
    return text(f'Hello, World! {datetime.utcnow().isoformat()}')


@allow_anonymous()
@app.route('/hello')
async def hello():
    return text('Hello!')


app.start()

