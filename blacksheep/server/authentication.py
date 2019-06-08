from guardpost.asynchronous.authentication import AuthenticationStrategy, AuthenticationHandler


__all__ = ('AuthenticationStrategy', 'AuthenticationHandler', 'get_authentication_middleware')


def get_authentication_middleware(strategy: AuthenticationStrategy):
    async def authentication_middleware(request, handler):

        await strategy.authenticate(request)

        return await handler(request)
    return authentication_middleware
