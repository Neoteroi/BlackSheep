

def middleware_partial(handler, next_handler):
    async def middleware_wrapper(request):
        return await handler(request, next_handler)
    return middleware_wrapper


def get_middlewares_chain(middlewares, handler):
    fn = handler
    for middleware in reversed(middlewares):
        fn = middleware_partial(middleware, fn)
    return fn
