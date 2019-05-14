import asyncio
import inspect
from typing import Union, List, TypeVar, Callable, Sequence, Set, Tuple
from inspect import Signature, Parameter, _empty
from blacksheep.server.routing import Route
from .bindings import (FromHeader,
                       FromJson,
                       FromQuery,
                       FromRoute,
                       FromServices,
                       Binder,
                       SyncBinder,
                       FromBody,
                       RequestBinder)


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


def get_parameter_binder(parameter, services, route):
    name = parameter.name

    if name == 'request':
        return RequestBinder()

    original_annotation = parameter.annotation

    if original_annotation is _empty:
        # 1. does route contain a parameter with matching name?
        if name in route.param_names:
            return FromRoute(str, name)

        # 2. do services contain a service with matching name?
        if name in services:
            return FromServices(name)

        # 3. default to query parameter
        return FromQuery(List[str], name)

    # unwrap the Optional[] annotation, if present:
    is_optional, annotation = _check_union(parameter, original_annotation, route.handler)

    # 1. is the type annotation already a binder?
    if isinstance(annotation, Binder):

        if not annotation.name:
            # force name == parameter name
            annotation.name = name

        if isinstance(annotation, FromRoute) and annotation.name not in route.param_names:
            raise RouteBinderMismatch(annotation.name, route)

        return annotation

    # 2A. do services contain a service with matching name?
    if name in services:
        return FromServices(name)

    # 2B. do services contain a service with matching type?
    if annotation in services:
        return FromServices(annotation)

    # 3. does route contain a parameter with matching name?
    if name in route.param_names:
        return FromRoute(annotation, name)

    # 4. is simple type?
    if annotation in _simple_types_handled_with_query:
        return FromQuery(annotation, name, required=not is_optional)

    # 5. from body
    return FromJson(annotation, required=not is_optional)


def get_binders(route, services):
    """Returns a list of binders to extract parameters for a request handler."""
    method = route.handler
    signature = Signature.from_callable(method)
    parameters = signature.parameters
    from_body_binder = None

    binders = []
    for parameter_name, parameter in parameters.items():
        binder = get_parameter_binder(parameter, services, route)
        if isinstance(binder, FromBody):
            if from_body_binder is None:
                from_body_binder = binder
            else:
                raise AmbiguousMethodSignatureError(method)
        binders.append(binder)
    return binders


def _copy_name_and_docstring(source_method, wrapper):
    if source_method is wrapper:
        return
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
        _copy_name_and_docstring(method, normalized)

    return normalized
