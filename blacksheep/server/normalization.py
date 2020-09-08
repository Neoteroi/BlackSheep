import inspect
from functools import wraps
from inspect import Signature, _empty  # type: ignore
from typing import Any, List, Sequence, Set, Type, Tuple, TypeVar, Union
from uuid import UUID

from guardpost.authentication import Identity, User

from blacksheep.normalization import copy_special_attributes

from .bindings import (
    empty,
    Binder,
    BodyBinder,
    BoundValue,
    ControllerBinder,
    ExactBinder,
    IdentityBinder,
    RequestBinder,
    QueryBinder,
    JsonBinder,
    RouteBinder,
    ServiceBinder,
    get_binder_by_type,
)

_next_handler_binder = object()


class NormalizationError(Exception):
    ...


class UnsupportedSignatureError(NormalizationError):
    def __init__(self, method):
        super().__init__(
            f"Cannot normalize method `{method.__qualname__}` because its "
            f"signature contains *args or *kwargs parameters. "
            f"If you use a decorator, please use `functools.@wraps` "
            f"with your wrapper, to fix this error."
        )


class MultipleFromBodyParameters(NormalizationError):
    def __init__(self, method, first_match, new_match):
        super().__init__(
            f"Cannot use more than one `FromBody` parameters for the same method "
            f"({method.__qualname__}). The first match was: {first_match}, "
            f"a second one {new_match}."
        )


class AmbiguousMethodSignatureError(NormalizationError):
    def __init__(self, method):
        super().__init__(
            f"Cannot normalize method `{method.__qualname__}` due to its "
            f"ambiguous signature. "
            f"Please specify exact binders for its arguments."
        )


class RouteBinderMismatch(NormalizationError):
    def __init__(self, parameter_name, route):
        super().__init__(
            f"The parameter {parameter_name} for method "
            f"{route.handler.__name__} is bound to route path, "
            f"but the route doesn`t contain a parameter with matching name."
        )


_types_handled_with_query = {
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
    UUID,
    List[UUID],
    Set[UUID],
    Tuple[UUID],
}


def _check_union(parameter, annotation, method):
    """
    Checks if the given annotation is Optional[] - in such case unwraps it
    and returns its value.

    An exception is thrown if other kinds of Union[] are used, since they are
    not supported by method normalization.
    In such case, the user of the library should read the desired value from
    the request object.
    """

    if hasattr(annotation, "__origin__") and annotation.__origin__ is Union:
        # support only Union[None, Type] - that is equivalent of Optional[Type]
        if type(None) not in annotation.__args__ or len(annotation.__args__) > 2:
            raise NormalizationError(
                f'Unsupported parameter type "{parameter.name}" '
                f'for method "{method.__name__}"; '
                f"only Optional types are supported for automatic binding. "
                f"Read the desired value from the request itself."
            )

        for possible_type in annotation.__args__:
            if type(None) is possible_type:
                continue
            return True, possible_type
    return False, annotation


def _get_parameter_binder_without_annotation(
    parameter, services, route, method, name: str
) -> Binder:
    if route:
        # 1. does route contain a parameter with matching name?
        if name in route.param_names:
            return RouteBinder(str, name, True)

    # 2. do services contain a service with matching name?
    if name in services:
        return ServiceBinder(name, name, True, services)

    # 3. default to query parameter
    return QueryBinder(List[str], name, True)


def _is_bound_value_annotation(annotation) -> bool:
    if inspect.isclass(annotation) and issubclass(annotation, BoundValue):
        return True
    return "__origin__" in annotation.__dict__ and issubclass(
        annotation.__dict__["__origin__"], BoundValue
    )


def _get_raw_bound_value_type(bound_type: Type[BoundValue]) -> Type[Any]:
    if hasattr(bound_type, "__args__"):
        return bound_type.__args__[0]  # type: ignore

    # the type can be a subclass of a type specifying the annotation
    if hasattr(bound_type, "__orig_bases__"):
        for subtype in bound_type.__orig_bases__:  # type: ignore
            if hasattr(subtype, "__args__"):
                return subtype.__args__[0]  # type: ignore
    return str


def _get_bound_value_type(bound_type: Type[BoundValue]) -> Type[Any]:
    value_type = _get_raw_bound_value_type(bound_type)

    if isinstance(value_type, TypeVar):
        # The user of the API did not specify a value type,
        # for example:
        #   def foo(x: FromQuery): ...
        return List[str]

    return value_type


def _get_parameter_binder(
    parameter: inspect.Parameter, services, route, method
) -> Binder:
    name = parameter.name

    if name == "request":
        return RequestBinder()

    if name == "services":
        return ExactBinder(services)

    original_annotation = parameter.annotation

    if original_annotation is _empty:
        return _get_parameter_binder_without_annotation(
            parameter, services, route, method, name
        )

    # unwrap the Optional[] annotation, if present:
    is_root_optional, annotation = _check_union(parameter, original_annotation, method)

    # 1. is the type annotation of BoundValue[T] type?
    if _is_bound_value_annotation(annotation):
        binder_type = get_binder_by_type(annotation)
        expected_type = _get_bound_value_type(annotation)

        is_optional, expected_type = _check_union(parameter, expected_type, method)

        parameter_name = annotation.name or name

        binder = binder_type(expected_type, parameter_name, False)
        binder.required = not is_optional

        if is_root_optional:
            binder.root_required = False

        if route:
            if (
                isinstance(binder, RouteBinder)
                and parameter_name not in route.param_names
            ):
                raise RouteBinderMismatch(parameter_name, route)

        if isinstance(binder, ServiceBinder):
            binder.services = services

        return binder

    # 2A. do services contain a service with matching name?
    if name in services:
        return ServiceBinder(name, name, True, services)

    # 2B. do services contain a service with matching type?
    if annotation in services:
        return ServiceBinder(annotation, annotation.__class__.__name__, True, services)

    # 3. does route contain a parameter with matching name?
    if route and name in route.param_names:
        return RouteBinder(annotation, name, True)

    # 4. is simple type?
    if annotation in _types_handled_with_query:
        return QueryBinder(annotation, name, True, required=not is_root_optional)

    # 5. is request user?
    if annotation is User or annotation is Identity:
        return IdentityBinder(
            annotation, name, implicit=True, required=not is_root_optional
        )

    # 6. from json body (last default)
    return JsonBinder(annotation, name, True, required=not is_root_optional)


def get_parameter_binder(
    parameter: inspect.Parameter, services, route, method
) -> Binder:
    binder = _get_parameter_binder(parameter, services, route, method)
    if parameter.default is _empty:
        binder.default = empty
    else:
        binder.default = parameter.default
    return binder


def _get_binders_for_function(method, services, route) -> List[Binder]:
    signature = Signature.from_callable(method)
    parameters = signature.parameters
    body_binder = None

    binders = []
    for parameter_name, parameter in parameters.items():
        if not route and parameter_name in {"handler", "next_handler"}:
            binders.append(_next_handler_binder)
            continue

        binder = get_parameter_binder(parameter, services, route, method)
        if isinstance(binder, BodyBinder):
            if body_binder is None:
                body_binder = binder
            else:
                raise AmbiguousMethodSignatureError(method)
        binders.append(binder)

    return binders


def get_binders(route, services) -> Sequence[Binder]:
    """
    Returns a list of binders to extract parameters
    for a request handler.
    """
    return _get_binders_for_function(route.handler, services, route)


def get_binders_for_middleware(method, services):
    return _get_binders_for_function(method, services, None)


def _copy_name_and_docstring(source_method, wrapper):
    try:
        wrapper.__name__ = source_method.__name__
        wrapper.__doc__ = source_method.__doc__
    except AttributeError:
        pass


def _get_sync_wrapper_for_controller(binders: Sequence[Binder], method):
    @wraps(method)
    async def handler(request):
        values = []
        controller = await binders[0].get_value(request)
        await controller.on_request(request)

        values.append(controller)

        for binder in binders[1:]:
            values.append(await binder.get_parameter(request))

        response = method(*values)
        await controller.on_response(response)
        return response

    return handler


def _get_async_wrapper_for_controller(binders: Sequence[Binder], method):
    @wraps(method)
    async def handler(request):
        values = []
        controller = await binders[0].get_value(request)
        await controller.on_request(request)

        values.append(controller)

        for binder in binders[1:]:
            values.append(await binder.get_parameter(request))

        response = await method(*values)
        await controller.on_response(response)
        return response

    return handler


def get_sync_wrapper(services, route, method, params, params_len):
    if params_len == 0:
        # the user defined a synchronous request handler with no input
        async def handler(_):
            return method()

        return handler

    if params_len == 1 and "request" in params:

        async def handler(request):
            return method(request)

        return handler

    binders = get_binders(route, services)

    if isinstance(binders[0], ControllerBinder):
        return _get_sync_wrapper_for_controller(binders, method)

    @wraps(method)
    async def handler(request):
        values = []
        for binder in binders:
            values.append(await binder.get_parameter(request))
        return method(*values)

    return handler


def get_async_wrapper(services, route, method, params, params_len):
    if params_len == 0:
        # the user defined a request handler with no input
        async def handler(_):
            return await method()

        return handler

    if params_len == 1 and "request" in params:
        # no need to wrap the request handler
        return method

    binders = get_binders(route, services)

    if isinstance(binders[0], ControllerBinder):
        return _get_async_wrapper_for_controller(binders, method)

    @wraps(method)
    async def handler(request):
        values = []
        for binder in binders:
            values.append(await binder.get_parameter(request))
        return await method(*values)

    return handler


def normalize_handler(route, services):
    method = route.handler

    sig = Signature.from_callable(method)
    params = sig.parameters
    params_len = len(params)

    if any(str(param).startswith("*") for param in params.values()):
        raise UnsupportedSignatureError(method)

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
    if first_one.name == "request" and second_one.name in {"handler", "next_handler"}:
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
                values.append(await binder.get_parameter(request))

        if _next_handler_binder in binders:
            # middleware that can continue the chain: control is left to it;
            # for example an authorization middleware can decide to now call
            # the next handler
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
        raise ValueError("Middlewares must be asynchronous functions")

    return normalized
