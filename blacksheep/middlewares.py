from blacksheep.normalization import copy_special_attributes


def middleware_partial(handler, next_handler):
    async def middleware_wrapper(request):
        return await handler(request, next_handler)

    return middleware_wrapper


def get_middlewares_chain(middlewares, handler):
    fn = handler
    for middleware in reversed(middlewares):
        if not middleware:
            continue
        wrapper_fn = middleware_partial(middleware, fn)
        setattr(wrapper_fn, "root_fn", handler)
        copy_special_attributes(fn, wrapper_fn)
        fn = wrapper_fn
    return fn
