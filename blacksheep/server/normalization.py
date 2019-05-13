import inspect
from typing import Union, List, TypeVar, Callable, Sequence, Set, Tuple
from inspect import Signature, Parameter, _empty
from blacksheep.server.routing import Route
from .bindings import FromHeader, FromJson, FromQuery, FromRoute, FromServices, Binder, SyncBinder, FromBody


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


# TODO: add type hints; services is Union[dict, rodi.Services]
def get_parameter_binder(parameter, services, route):
    name = parameter.name
    annotation = parameter.annotation

    if annotation is _empty:
        # 1. does route contain a parameter with matching name?
        if name in route.param_names:
            return FromRoute(str, name)

        # 2. do services contain a service with matching name?
        if name in services:
            return FromServices(name)

        # 3. default to query parameter
        return FromQuery(List[str], name)

    # 1. is the type annotation already a binder?
    if isinstance(annotation, Binder):
        if isinstance(annotation, FromRoute) and name not in route.param_names:
            raise RouteBinderMismatch(name, route)

        # force name == parameter name
        annotation.name = name
        return annotation

    # 2A. do services contain a service with matching name?
    if name in services:
        return FromServices(name)

    # 2B. do services contain a service with matching type?
    if annotation in services:
        return FromServices(annotation)

    # 3. is simple type?
    if annotation in _simple_types_handled_with_query:
        return FromQuery(annotation, name)

    # 3. from body
    return FromJson(annotation, True)


def get_binders(route, services):
    """Returns a list of binders to extract parameters for a request handler"""
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


def normalize_handler(route, services):
    method = route.handler
    signature = Signature.from_callable(method)
    parameters = signature.parameters
    parameters_len = len(parameters)

    binders = []
    normalized_parameters = {}

    for parameter_name, parameter in parameters.items():
        binder = get_parameter_binder(parameter, services, route)
        if parameter.annotation is _empty:
            print('No type annotation, get default')
        print(parameter)

    #if inspect.iscoroutinefunction(method):
    #    return get_async_wrapper(services, method, params, params_len)

    #return get_sync_wrapper(services, method, params, params_len)