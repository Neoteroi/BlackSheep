import inspect
from typing import Union, List, Sequence, Set, Tuple
from inspect import Signature, _empty
from .bindings import (FromJson,
                       FromQuery,
                       FromRoute,
                       FromServices,
                       Binder,
                       FromBody,
                       RequestBinder,
                       ExactBinder)
from blacksheep.normalization import copy_special_attributes


_next_handler_binder = object()


class NormalizationError(Exception):
    pass


class MultipleFromBodyBinders(NormalizationError):

    def __init__(self, method, first_match, new_match):
        super().__init__(f'Cannot use more than one `FromBody` binder for the same method ({method.__name__}). '
                         f'The first match was: {first_match}, a second one {new_match}.')


class AmbiguousMethodSignatureError(NormalizationError):

    def __init__(self, method):
        super().__init__(f'Cannot normalize method {method.__name__} due to its ambiguous signature. '
                         f'Please specify exact binders for its arguments.')


class RouteBinderMismatch(NormalizationError):

    def __init__(self, parameter_name, route):
        super().__init__(f'The parameter {parameter_name} for method {route.handler.__name__} is bound to route path, '
                         f'but the route doesn`t contain a parameter with matching name.')


def get_from_body_parameter(method) -> FromBody:
    """Extracts a single FromBody parameter from the given signature,
    throwing exception if more than one is defined."""
    sig = Signature.from_callable(method)

    from_body_parameter = None

    for name, parameter in sig.parameters.items():
        if isinstance(parameter.annotation, FromBody):
            if from_body_parameter is None:
                from_body_parameter = parameter.annotation
            else:
                raise MultipleFromBodyBinders(method, from_body_parameter, parameter)

    return from_body_parameter


_simple_types_handled_with_query = {
    str,
    int,
    float,
    bool,
    list,
    set,
    tuple,
    List[str],
    List[int],
    List[float],
    List[bool],
    Sequence[str],
    Sequence[int],
    Sequence[float],
    Sequence[bool],
    Set[str],
    Set[int],
    Set[float],
    Set[bool],
    Tuple[str],
    Tuple[int],
    Tuple[float],
    Tuple[bool],
}


def _check_union(parameter, annotation, method):
    """Checks if the given annotation is Optional[] - in such case unwraps it and returns its value

    An exception is thrown if other kinds of Union[] are used, since they are not supported by method normalization.
    In such case, the user of the library should read the desired value from the request object.
    """

    if hasattr(annotation, '__origin__') and annotation.__origin__ is Union:
        # support only Union[None, Type] - that is equivalent of Optional[Type]
        if type(None) not in annotation.__args__ or len(annotation.__args__) > 2:
            raise NormalizationError(f'Unsupported parameter type "{parameter.name}" for method "{method.__name__}"; '
                                     f'only Optional types are supported for automatic binding. '
                                     f'Read the desired value from the request itself.')

        for possible_type in annotation.__args__:
            if type(None) is possible_type:
                continue
            return True, possible_type
    return False, annotation


def get_parameter_binder(parameter, services, route, method):
    name = parameter.name

    if name == 'request':
        return RequestBinder()

    if name == 'services':
        return ExactBinder(services)

    original_annotation = parameter.annotation

    if original_annotation is _empty:
        if route:
            # 1. does route contain a parameter with matching name?
            if name in route.param_names:
                return FromRoute(str, name)

        # 2. do services contain a service with matching name?
        if name in services:
            return FromServices(name, services)

        # 3. default to query parameter
        return FromQuery(List[str], name)

    # unwrap the Optional[] annotation, if present:
    is_optional, annotation = _check_union(parameter, original_annotation, method)

    # 1. is the type annotation already a binder?
    if isinstance(annotation, Binder):

        if not annotation.name:
            # force name == parameter name
            annotation.name = name

        if route:
            if isinstance(annotation, FromRoute) and annotation.name not in route.param_names:
                raise RouteBinderMismatch(annotation.name, route)

        if isinstance(annotation, FromServices):
            annotation.services = services

        return annotation

    # 2A. do services contain a service with matching name?
    if name in services:
        return FromServices(name, services)

    # 2B. do services contain a service with matching type?
    if annotation in services:
        return FromServices(annotation, services)

    # 3. does route contain a parameter with matching name?
    if route and name in route.param_names:
        return FromRoute(annotation, name)

    # 4. is simple type?
    if annotation in _simple_types_handled_with_query:
        return FromQuery(annotation, name, required=not is_optional)

    # 5. from body
    return FromJson(annotation, required=not is_optional)


def _get_binders_for_method(method, services, route):
    signature = Signature.from_callable(method)
    parameters = signature.parameters
    from_body_binder = None

    binders = []
    for parameter_name, parameter in parameters.items():
        if not route and parameter_name in {'handler', 'next_handler'}:
            binders.append(_next_handler_binder)
            continue

        binder = get_parameter_binder(parameter, services, route, method)
        if isinstance(binder, FromBody):
            if from_body_binder is None:
                from_body_binder = binder
            else:
                raise AmbiguousMethodSignatureError(method)
        binders.append(binder)
    return binders


def get_binders(route, services):
    """Returns a list of binders to extract parameters for a request handler."""
    return _get_binders_for_method(route.handler, services, route)


def get_binders_for_middleware(method, services):
    return _get_binders_for_method(method, services, None)


def _copy_name_and_docstring(source_method, wrapper):
    wrapper.__name__ = source_method.__name__
    wrapper.__doc__ = source_method.__doc__


def get_sync_wrapper(services, route, method, params, params_len):
    if params_len == 0:
        # the user defined a synchronous request handler with no input
        async def handler(_):
            return method()

        return handler

    if params_len == 1 and 'request' in params:
        async def handler(request):
            return method(request)

        return handler

    binders = get_binders(route, services)

    async def handler(request):
        values = []
        for binder in binders:
            values.append(await binder.get_value(request))
        return method(*values)

    return handler


def get_async_wrapper(services, route, method, params, params_len):
    if params_len == 0:
        # the user defined a request handler with no input
        async def handler(_):
            return await method()

        return handler

    if params_len == 1 and 'request' in params:
        # no need to wrap the request handler
        return method

    binders = get_binders(route, services)

    async def handler(request):
        values = []
        for binder in binders:
            values.append(await binder.get_value(request))
        return await method(*values)

    return handler


def normalize_handler(route, services):
    method = route.handler

    sig = Signature.from_callable(method)
    params = sig.parameters
    params_len = len(params)

    if inspect.iscoroutinefunction(method):
        normalized = get_async_wrapper(services, route, method, params, params_len)
    else:
        normalized = get_sync_wrapper(services, route, method, params, params_len)

    if normalized is not method:
        copy_special_attributes(method, normalized)
        _copy_name_and_docstring(method, normalized)

    return normalized


def _is_basic_middleware_signature(parameters):
    values = list(parameters.values())

    if len(values) != 2:
        return False

    first_one = values[0]
    second_one = values[1]
    if first_one.name == 'request' and second_one.name in {'handler', 'next_handler'}:
        return True
    return False


def _get_middleware_async_binder(method, services):
    binders = get_binders_for_middleware(method, services)

    async def handler(request, next_handler):
        values = []
        for binder in binders:
            if binder is _next_handler_binder:
                values.append(next_handler)
            else:
                values.append(await binder.get_value(request))

        if _next_handler_binder in binders:
            # middleware that can continue the chain: control is left to it;
            # for example an authorization middleware can decide to now call the next handler
            return await method(*values)

        # middleware that cannot continue the chain, so we continue it here
        await method(*values)
        return await next_handler(request)

    return handler


def normalize_middleware(middleware, services):
    sig = Signature.from_callable(middleware)
    params = sig.parameters

    if _is_basic_middleware_signature(params):
        return middleware

    if inspect.iscoroutinefunction(middleware):
        normalized = _get_middleware_async_binder(middleware, services)
    else:
        raise ValueError('Middlewares must be asynchronous functions')

    return normalized
