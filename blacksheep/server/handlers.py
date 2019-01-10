import inspect
from typing import Union, List, TypeVar, Callable
from inspect import Signature, Parameter, _empty
from blacksheep.exceptions import BadRequest


def get_param(request, name):
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


def parse_value(value, desired_type: type, param_name: str):
    try:
        if desired_type is bool:
            return bool(int(value))
        if desired_type in {int, float}:
            return desired_type(value)
        return value
    except ValueError:
        raise BadRequest(f'invalid parameter "{param_name}". '
                         f'The value cannot be parsed as {desired_type.__name__}.')


class ParamDelegate:
    __slots__ = ('name',
                 'annotation',
                 'is_optional')

    def __init__(self, name: str, annotation: type, is_optional: bool):
        self.name = name
        self.annotation = annotation
        self.is_optional = is_optional

    def __call__(self, request):
        value = get_param(request, self.name)

        if value is None or value == '':
            if self.is_optional:
                return None

            raise BadRequest(f'missing parameter: {self.name}.')

        if self.annotation is str:
            return unwrap(value)

        return value


class ListParamDelegate(ParamDelegate):
    __slots__ = ('name',
                 'annotation',
                 'is_optional',
                 'item_type')

    def __init__(self,
                 name: str,
                 annotation: type,
                 is_optional: bool,
                 item_type: type):
        super().__init__(name, annotation, is_optional)
        self.item_type = item_type

    def __call__(self, request):
        value = super().__call__(request)

        if value is None:
            return value

        if self.item_type in {int, float, bool}:
            return [parse_value(item, self.item_type, self.name) for item in get_list(value)]
        return get_list(value)


class ParsedParamDelegate(ParamDelegate):
    __slots__ = ('name',
                 'annotation',
                 'is_optional')

    def __call__(self, request):
        value = super().__call__(request)

        if value is None:
            return value

        return parse_value(unwrap(value), self.annotation, self.name)


def _check_union(method: Callable, param: Parameter):
    annotation = param.annotation
    if annotation is not _empty:
        if hasattr(annotation, '__origin__') and annotation.__origin__ is Union:
            if type(None) not in annotation.__args__ or len(annotation.__args__) > 2:
                raise RuntimeError(f'Invalid parameter "{param.name}" for method "{method.__name__}"; '
                                   f'only Optional types are supported for automatic binding;')

            for possible_type in annotation.__args__:
                if type(None) is possible_type:
                    continue
                return True, possible_type
    return False, annotation


def get_param_delegate(services, method: Callable, param: Parameter):
    if param.name == 'request':
        return lambda request: request

    is_optional, param_type = _check_union(method, param)

    if services:
        if param_type in services:
            return lambda request: services.get(param_type)
        if param.name in services:
            return lambda request: services.get(param.name)

    if param_type in {int, float, bool}:
        return ParsedParamDelegate(param.name, param_type, is_optional)

    if hasattr(param_type, '__origin__') and param_type.__origin__ is list:  # List type
        item_type = param_type.__args__[0]

        if isinstance(item_type, TypeVar):
            # List annotation without child type
            item_type = str

        return ListParamDelegate(param.name, param_type, is_optional, item_type)

    return ParamDelegate(param.name, param_type, is_optional)


def get_sync_wrapper(services, method, params, params_len):
    if params_len == 0:
        # the user defined a synchronous request handler with no input
        async def handler(_):
            return method()

        return handler

    if params_len == 1 and 'request' in params:
        async def handler(request):
            return method(request)

        return handler

    params_extractors = [get_param_delegate(services, method, param) for param in params.values()]

    async def handler(request):
        return await method(*[delegate(request) for delegate in params_extractors])

    return handler


def get_async_wrapper(services, method, params, params_len):
    if params_len == 0:
        # the user defined a request handler with no input
        async def handler(_):
            return await method()

        return handler

    if params_len == 1 and 'request' in params:
        # no need to wrap the request handler
        return method

    params_extractors = [get_param_delegate(services, method, param) for param in params.values()]

    async def handler(request):
        return await method(*[delegate(request) for delegate in params_extractors])

    return handler


def normalize_handler(services, method):
    sig = Signature.from_callable(method)
    params = sig.parameters
    params_len = len(params)

    if inspect.iscoroutinefunction(method):
        return get_async_wrapper(services, method, params, params_len)

    return get_sync_wrapper(services, method, params, params_len)
