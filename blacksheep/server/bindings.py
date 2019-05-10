"""
This module implements a feature inspired by "Model Binding" in ASP.NET web framework.
It provides a strategy to have request parameters read an injected into request handlers calls.
This feature is also useful to generate OpenAPI Documentation (Swagger) automatically (not implemented, yet).

See:
    https://docs.microsoft.com/en-us/aspnet/core/mvc/models/model-binding?view=aspnetcore-2.2
"""
from abc import ABC, abstractmethod
from typing import TypeVar, Optional, Callable, Sequence
from urllib.parse import unquote
from blacksheep import Request
from blacksheep.exceptions import BadRequest


T = TypeVar('T')


def _inspect_is_list_typing(expected_type):
    return hasattr(expected_type, '__origin__') and expected_type.__origin__ is list


def _generalize_init_type_error_message(ex: TypeError) -> str:
    return str(ex)\
        .replace('__init__() ', '')\
        .replace('keyword argument', 'parameter') \
        .replace('keyword arguments', 'parameters') \
        .replace('positional arguments', 'parameters')\
        .replace('positional argument', 'parameter')


class Binder(ABC):

    def __init__(self,
                 expected_type: T,
                 required: bool = True,
                 converter: Optional[Callable] = None):
        self.expected_type = expected_type
        self.required = required
        self.converter = converter

    @abstractmethod
    async def get_value(self, request: Request) -> T:
        pass


class MissingBodyError(BadRequest):

    def __init__(self):
        super().__init__('Missing body payload')


class MissingParameterError(BadRequest):

    def __init__(self, name: str, source: str):
        super().__init__(f'Missing parameter `{name}` from {source}')


class InvalidRequestBody(BadRequest):

    def __init__(self, description: Optional[str] = 'Invalid body payload'):
        super().__init__(description)


class MissingConverterError(RuntimeError):

    def __init__(self, expected_type, binder_type):
        super().__init__(f'Cannot determine a default converter for type `{str(expected_type)}`. '
                         f'Please define a converter method for this binder ({binder_type.__name__}).')


class FromJson(Binder):

    def __init__(self,
                 expected_type: T,
                 required: bool = False,
                 converter: Optional[Callable] = None
                 ):
        if not converter:
            def default_converter(data):
                return expected_type(**data)
            converter = default_converter

        super().__init__(expected_type, required, converter)

    def parse_value(self, data: dict) -> T:
        try:
            return self.converter(data)
        except TypeError as te:
            raise InvalidRequestBody(_generalize_init_type_error_message(te))
        except ValueError as ve:
            raise InvalidRequestBody(str(ve))

    async def get_value(self, request: Request) -> T:
        if request.declares_json():
            data = await request.json()

            if not data:
                raise MissingBodyError()

            return self.parse_value(data)

        if self.required:
            if not request.has_body():
                raise MissingBodyError()

            raise InvalidRequestBody('Expected JSON payload')

        return None


def _default_bool_binder(values: Sequence[str]):
    if not values:
        return None

    value = values[0].lower()

    if value in {'1', 'true'}:
        return True

    if value in {'0', 'false'}:
        return False

    # bad request: expected a bool value, but
    # got something different that is not handled
    raise BadRequest()


class SyncBinder(Binder):
    """Base binder class for values that can be read synchronously from requests with complete headers.
    Like route, query string and header parameters.
    """

    _simple_types = {int, float, bool}

    def __init__(self,
                 name: str,
                 expected_type: T,
                 required: bool = False,
                 converter: Optional[Callable] = None):
        super().__init__(expected_type, required, converter or self._get_default_converter(expected_type))
        self.name = name

    def _get_default_converter(self, expected_type):
        if expected_type is str:
            return lambda value: unquote(value[0])

        if expected_type is bool:
            return _default_bool_binder

        if expected_type is bytes:
            return lambda value: value[0]

        if expected_type in self._simple_types:
            return lambda value: expected_type(value[0])

        raise MissingConverterError(expected_type, self.__class__)

    @abstractmethod
    def get_raw_value(self, request: Request) -> Sequence[str]:
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        pass

    async def get_value(self, request: Request) -> T:
        raw_value = self.get_raw_value(request)
        try:
            value = self.converter(raw_value)
        except BadRequest:
            raise BadRequest(f'Invalid value for parameter `{self.name}`')

        if value is None:
            if self.required:
                raise MissingParameterError(self.name, self.source_name)
            return None

        return value


class FromHeader(SyncBinder):

    @property
    def source_name(self) -> str:
        return 'header'

    def get_raw_value(self, request: Request) -> Sequence[str]:
        return [header.value.decode('utf8') for header in request.headers[self.name.encode()]]


class FromQuery(SyncBinder):

    @property
    def source_name(self) -> str:
        return 'query'

    def get_raw_value(self, request: Request) -> Sequence[str]:
        return [value for value in request.query.get(self.name, [])]


class FromRoute(SyncBinder):

    def get_raw_value(self, request: Request) -> Sequence[str]:
        return [request.route_values.get(self.name, '')]

    @property
    def source_name(self) -> str:
        return 'route'
