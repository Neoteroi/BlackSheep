from typing import Optional, Dict
from blacksheep import Response, Headers, Header, TextContent
from guardpost.authorization import AuthorizationError
from guardpost.asynchronous.authentication import AuthenticationStrategy, AuthenticationHandler


__all__ = ('AuthenticationStrategy',
           'AuthenticationHandler',
           'AuthenticateChallenge',
           'get_authentication_middleware',
           'handle_authentication_challenge')


def get_authentication_middleware(strategy: AuthenticationStrategy):
    async def authentication_middleware(request, handler):

        await strategy.authenticate(request, getattr(handler, 'auth_schemes', None))

        return await handler(request)
    return authentication_middleware


class AuthenticateChallenge(AuthorizationError):
    header_name = b'WWW-Authenticate'

    def __init__(self,
                 scheme: str,
                 realm: Optional[str],
                 parameters: Optional[Dict[str, str]]):
        self.scheme = scheme
        self.realm = realm
        self.parameters = parameters

    def _get_header_value(self) -> bytes:
        if not self.realm and not self.parameters:
            return self.scheme.encode()

        parts = bytearray(self.scheme.encode())
        if self.realm:
            parts.extend(f' realm="{self.realm}"'.encode())

        if self.parameters:
            parts.extend(b', ')
            parts.extend(b', '.join([f'{key}="{value}"'.encode() for key, value in self.parameters.items()]))
        return bytes(parts)

    def get_header(self) -> Header:
        return Header(self.header_name, self._get_header_value())


async def handle_authentication_challenge(app, request, exception: AuthenticateChallenge):
    return Response(401,
                    Headers([exception.get_header()]),
                    content=TextContent('Unauthorized'))
