"""
This module implements a feature inspired by "Model Binding" in ASP.NET web framework.
It provides a strategy to have request parameters read an injected into request handlers calls.
This feature is also useful to generate OpenAPI Documentation (Swagger) automatically (not implemented, yet).

See:
    https://docs.microsoft.com/en-us/aspnet/core/mvc/models/model-binding?view=aspnetcore-2.2
"""
from abc import ABC, abstractmethod
from collections.abc import Iterable as IterableAbc
from typing import Type, TypeVar, Optional, Callable, Sequence, Union, List
from urllib.parse import unquote
from blacksheep import Request
from blacksheep.exceptions import BadRequest
from rodi import Services, GetServiceContext


T = TypeVar('T')
TypeOrName = Union[Type, str]


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
        self.name = None

    @abstractmethod
    async def get_value(self, request: Request) -> T:
        pass

    def __repr__(self):
        return f'<{self.__class__.__name__} {self.expected_type} at {id(self)}>'


class MissingBodyError(BadRequest):

    def __init__(self):
        super().__init__('Missing body payload')


class MissingParameterError(BadRequest):

    def __init__(self, name: str, source: str):
        super().__init__(f'Missing parameter `{name}` from {source}')


class InvalidRequestBody(BadRequest):

    def __init__(self, description: Optional[str] = 'Invalid body payload'):
        super().__init__(description)


class MissingConverterError(Exception):

    def __init__(self, expected_type, binder_type):
        super().__init__(f'A default converter for type `{str(expected_type)}` is not configured. '
                         f'Please define a converter method for this binder ({binder_type.__name__}).')


class FromBody(Binder):

    _excluded_methods = {'GET', 'HEAD', 'TRACE'}


class FromJson(FromBody):

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
        if request.declares_json() and request.method not in self._excluded_methods:
            data = await request.json()

            if not data:
                raise MissingBodyError()

            return self.parse_value(data)

        if self.required:
            if not request.has_body():
                raise MissingBodyError()

            raise InvalidRequestBody('Expected JSON payload')

        return None


def _default_bool_converter(value: str):
    if value in {'1', 'true'}:
        return True

    if value in {'0', 'false'}:
        return False

    # bad request: expected a bool value, but
    # got something different that is not handled
    raise BadRequest()


def _default_bool_list_converter(values: Sequence[str]):
    return _default_bool_converter(values[0].lower()) if values else None


def _default_str_binder(values: Sequence[str]):
    if not values:
        return None
    return unquote(values[0])


def _default_simple_types_binder(expected_type: Type, values: Sequence[str]):
    return expected_type(values[0]) if values else None


class SyncBinder(Binder):
    """Base binder class for values that can be read synchronously from requests with complete headers.
    Like route, query string and header parameters.
    """

    _simple_types = {int, float, bool}

    def __init__(self,
                 expected_type: T = List[str],
                 name: str = None,
                 required: bool = False,
                 converter: Optional[Callable] = None):
        super().__init__(expected_type, required, converter or self._get_default_converter(expected_type))
        self.name = name

    def __repr__(self):
        return f'<{self.__class__.__name__} "{self.name}" at {id(self)}>'

    def _get_default_converter_single(self, expected_type):
        if expected_type is str:
            return lambda value: unquote(value) if value else None

        if expected_type is bool:
            return _default_bool_converter

        if expected_type is bytes:
            return lambda value: value if value else None

        if expected_type in self._simple_types:
            return lambda value: expected_type(value) if value else None

        raise MissingConverterError(expected_type, self.__class__)

    def _get_default_converter_for_iterable(self, expected_type):
        generic_type = self._get_type_for_generic_iterable(expected_type)
        item_type = self._generic_iterable_annotation_item_type(expected_type)
        item_converter = self._get_default_converter_single(item_type)
        return lambda values: generic_type(item_converter(value) for value in values)

    def _get_default_converter(self, expected_type):
        if expected_type is str:
            return lambda value: unquote(value[0]) if value else None

        if expected_type is bool:
            return _default_bool_list_converter

        if expected_type is bytes:
            return lambda value: value[0] if value else None

        if expected_type in self._simple_types:
            return lambda value: expected_type(value[0]) if value else None

        if self._is_generic_iterable_annotation(expected_type) or expected_type in {list, set, tuple}:
            return self._get_default_converter_for_iterable(expected_type)

        raise MissingConverterError(expected_type, self.__class__)

    def _get_type_for_generic_iterable(self, expected_type):
        if expected_type in {list, tuple, set}:
            return expected_type

        origin = expected_type.__origin__
        if origin in {list, tuple, set}:
            return origin
        # here we cannot make something perfect: if the user of the library wants something better,
        # a converter should be specified when configuring binders; here the code defaults to list
        # for all abstract types (typing.Sequence, Set, etc.) even though not perfect
        return list

    def _is_generic_iterable_annotation(self, param_type):
        return hasattr(param_type, '__origin__') and (param_type.__origin__ in {list, tuple, set}
                                                      or issubclass(param_type.__origin__, IterableAbc))

    def _generic_iterable_annotation_item_type(self, param_type):
        try:
            item_type = param_type.__args__[0]
        except (IndexError, AttributeError):
            return str

        if isinstance(item_type, TypeVar):
            return str
        return item_type

    @abstractmethod
    def get_raw_value(self, request: Request) -> Sequence[str]:
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        pass

    _empty_iterables = [list(), set(), tuple()]

    def _empty_iterable(self, value):
        return value in self._empty_iterables

    async def get_value(self, request: Request) -> T:
        raw_value = self.get_raw_value(request)
        try:
            value = self.converter(raw_value)
        except (ValueError, BadRequest):
            raise BadRequest(f'Invalid value for parameter `{self.name}`; expected {self.expected_type}')

        if value is None and self.required:
            raise MissingParameterError(self.name, self.source_name)

        if not self.required and self._empty_iterable(value):
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

    def __init__(self,
                 expected_type: T = str,
                 name: str = None,
                 required: bool = False,
                 converter: Optional[Callable] = None):
        super().__init__(expected_type, name, required, converter)

    def get_raw_value(self, request: Request) -> Sequence[str]:
        return [request.route_values.get(self.name, '')]

    @property
    def source_name(self) -> str:
        return 'route'


class FromServices(Binder):

    def __init__(self, service: TypeOrName, services: Optional[Services] = None):
        super().__init__(service, False, None)
        self.services = services

    async def get_value(self, request: Request) -> T:
        try:
            context = request.services_context
        except AttributeError:
            # no support for scoped services (across parameters and middlewares)
            context = None

        return self.services.get(self.expected_type, context)


class RequestBinder(Binder):

    def __init__(self):
        super().__init__(Request)

    async def get_value(self, request: Request) -> T:
        return request


class ExactBinder(Binder):

    def __init__(self, exact_object):
        super().__init__(object)
        self.exact_object = exact_object

    async def get_value(self, request: Request):
        return self.exact_object
