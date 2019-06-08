from typing import Optional
from guardpost.asynchronous.authorization import AuthorizationStrategy


__all__ = ('auth',
           'AuthorizationStrategy',
           'allow_anonymous',
           'get_authorization_middleware')


def auth(policy: Optional[str] = None):
    """Configures authorization for a decorated request handler, optionally with a policy.
    If no policy is specified, the default policy of the configured AuthorizationStrategy is used.

    :param policy: optional, name of the policy to use to achieve authorization.
    """
    def decorator(f):
        f.auth = True
        f.auth_policy = policy
        return f
    return decorator


def anonymous():
    """Configures a decorated request handler, to be usable only for non authenticated users.

    TODO"""


def allow_anonymous():
    """Configures a decorated request handler, to be usable for all users: anonymous and authenticated users."""
    def decorator(f):
        f.allow_anonymous = True
        return f
    return decorator


def get_authorization_middleware(strategy: AuthorizationStrategy):
    async def authorization_middleware(request, handler):
        identity = request.identity
        # TODO: think if this solution is acceptable

        if hasattr(handler, 'allow_anonymous'):
            return await handler(request)

        if hasattr(handler, 'auth'):
            # function decorated by auth;
            await strategy.authorize(handler.auth_policy, identity)
        else:
            # function not decorated by auth;
            # TODO: continue from here
            # TODO: by default, do not require authorization when methods are not decorated
            # TODO: if the strategy is configured to use authorization by default, then require an authenticated user
            pass
            # await strategy.authorize(None, identity)

        return await handler(request)
    return authorization_middleware
