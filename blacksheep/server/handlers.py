import inspect
from typing import Union, List, TypeVar
from inspect import Signature, Parameter, _empty
from blacksheep.exceptions import BadRequest

# TODO: improve the design of following code:
#   1. it should be cleaner
#   2. inspections should run only once at startup; generating functions that go straight to the point (like rodi)


def extract_param_str(request, name: str) -> Union[List[str], str]:
    if name == 'request':
        return request

    if name in request.route_values:
        return request.route_values.get(name)

    return request.query.get(name)  # value is a list of strings


def unwrap(value):
    if isinstance(value, list):
        if len(value) == 1:
            return value[0]
        return None
    return value


def get_list(value):
    if isinstance(value, list):
        return value
    return [value]


def parse_value(value, desired_type):
    if desired_type is bool:
        return bool(int(value))
    if desired_type in {int, float}:
        return desired_type(value)
    return value


def handle_param_type(value, param, param_type):
    # if we get here, we don't accept None type, because a parameter was not annotated as optional
    if value is None:
        raise BadRequest(f'missing parameter: {param.name}.')

    if param_type is list:
        return get_list(value)

    if hasattr(param_type, '__origin__') and param_type.__origin__ is list:  # List type
        item_type = param_type.__args__[0]

        if isinstance(item_type, TypeVar):
            # List annotation without child type
            return get_list(value)

        if type(value) is list:
            if item_type is str:
                return get_list(value)

            if item_type in {int, float, bool}:
                try:
                    return [parse_value(unwrap(item), item_type) for item in get_list(value)]
                except ValueError:
                    raise BadRequest(f'invalid parameter "{param.name}". '
                                     f'The value contains an item that cannot be parsed as {item_type.__name__}.')
            return value

    if param_type in {int, float, bool}:
        try:
            return parse_value(unwrap(value), param_type)
        except ValueError:
            raise BadRequest(f'invalid parameter "{param.name}". '
                             f'The value cannot be parsed as {param_type.__name__}.')
    return value


def extract_param(request, param: Parameter):
    value = extract_param_str(request, param.name)
    annotation = param.annotation
    if annotation is not _empty and annotation is not str:
        if hasattr(annotation, '__origin__') and annotation.__origin__ is Union:
            possible_types = annotation.__args__
            if type(None) in possible_types and value is None:
                # handling of Optional type hint (or anyway Union containing None)
                return None

            # NB: BlackSheep type annotations handling only supports one type when multiple are defined;
            # TODO: throw exception in this scenario?
            for possible_type in possible_types:
                if type(None) is possible_type:
                    continue
                return handle_param_type(value, param, possible_type)

        return handle_param_type(value, param, annotation)

    return value


def get_sync_wrapper(method, params, params_len):
    if params_len == 0:
        # the user defined a synchronous request handler with no input
        async def handler(_):
            return method()
        return handler

    if params_len == 1 and 'request' in params:
        async def handler(request):
            return method(request)
        return handler

    async def handler(request):
        return method(*[extract_param(request, param) for param in params.values()])

    return handler


def get_async_wrapper(method, params, params_len):
    if params_len == 0:
        # the user defined a request handler with no input
        async def handler(_):
            return await method()

        return handler

    if params_len == 1 and 'request' in params:
        # no need to wrap the request handler
        return method

    async def handler(request):
        return await method(*[extract_param(request, param) for param in params.values()])

    return handler


def normalize_handler(method):
    sig = Signature.from_callable(method)
    params = sig.parameters
    params_len = len(params)

    if inspect.iscoroutinefunction(method):
        return get_async_wrapper(method, params, params_len)

    return get_sync_wrapper(method, params, params_len)
