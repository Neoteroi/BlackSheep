"""
This module implements a feature inspired by "Model Binding" in ASP.NET web framework.
It provides a strategy to have request parameters read an injected into request
handlers calls. This feature is also useful to generate OpenAPI Documentation (Swagger)
automatically (not implemented, yet).

See:
    https://docs.microsoft.com/en-us/aspnet/core/mvc/models/model-binding?view=aspnetcore-2.2
"""
from abc import abstractmethod
from collections.abc import Iterable as IterableAbc
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Generic,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)
from uuid import UUID
from urllib.parse import unquote

from guardpost.authentication import Identity
from rodi import Services

from blacksheep import Request
from blacksheep.exceptions import BadRequest

T = TypeVar("T")
TypeOrName = Union[Type, str]


empty = object()


class BindingException(Exception):
    pass


class BinderAlreadyDefinedException(BindingException):
    def __init__(self, class_name: str, overriding_class_name: str) -> None:
        super().__init__(
            f"There is already a binder defined for {class_name}. "
            f"The second type is: {overriding_class_name}"
        )


class BinderNotRegisteredForValueType(BindingException):
    def __init__(self, value_type: Type["BoundValue"]) -> None:
        super().__init__(
            f"There is no binder to handle: {value_type}. "
            f"To resolve, define a Binder class with `handle` class attribute "
            f"referencing {value_type}."
        )


class BinderMeta(type):
    handlers: Dict[Type[Any], Type["Binder"]] = {}

    def __init__(cls, name, bases, attr_dict):
        super().__init__(name, bases, attr_dict)
        handle = getattr(cls, "handle", None)

        if handle:
            if handle in cls.handlers:
                raise BinderAlreadyDefinedException(handle, name)
            cls.handlers[handle] = cls  # type: ignore


def _generalize_init_type_error_message(ex: TypeError) -> str:
    return (
        str(ex)
        .replace("__init__() ", "")
        .replace("keyword argument", "parameter")
        .replace("keyword arguments", "parameters")
        .replace("positional arguments", "parameters")
        .replace("positional argument", "parameter")
    )


class BoundValue(Generic[T]):
    """Base class for parameters that are bound for a web request."""

    name: Optional[str] = None

    def __init__(self, value: T) -> None:
        self._value = value

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self._value})>"

    @property
    def value(self) -> T:
        return self._value


class FromHeader(BoundValue[T]):
    """
    A parameter obtained from request headers.
    """


class FromQuery(BoundValue[T]):
    """
    A parameter obtained from URL query parameters.
    """


class FromServices(BoundValue[T]):
    """
    A parameter obtained from configured application services.
    """


class FromJson(BoundValue[T]):
    """
    A parameter obtained from JSON request body.
    """


class FromForm(BoundValue[T]):
    """
    A parameter obtained from Form request body: either
    application/x-www-form-urlencoded or multipart/form-data.
    """


class FromRoute(BoundValue[T]):
    """
    A parameter obtained from URL path fragment.
    """


class ClientInfo(BoundValue[Tuple[str, int]]):
    """
    Client ip and port information obtained from a request scope.
    """


class ServerInfo(BoundValue[Tuple[str, int]]):
    """
    Server ip and port information obtained from a request scope.
    """


class RequestUser(BoundValue[Identity]):
    """
    Returns the identity of the user that initiated the web request.
    This value is obtained from the configured authentication strategy.
    """


class Binder(metaclass=BinderMeta):
    handle: ClassVar[Type[BoundValue]]
    _implicit: bool
    default: Optional[T]

    def __init__(
        self,
        expected_type: T,
        name: str = "",
        implicit: bool = False,
        required: bool = True,
        converter: Optional[Callable] = None,
    ):
        self._implicit = implicit
        self.parameter_name = name
        self.expected_type = expected_type
        self.required = required
        self.root_required = True
        self.converter = converter
        self.default = empty

    @property
    def implicit(self) -> bool:
        return self._implicit

    async def get_parameter(self, request: Request) -> Union[T, BoundValue[T]]:
        """
        Gets a parameter to be passed to a request handler.

        The parameter can be equal to the value, when a binder is applied implicitly,
        or a BoundValue[T] when a binder is applied explicitly.

        Example:

            @app("/:id")
            def example(id: FromRoute[str]):
                # here id is an instance of FromRoute because the annotation is
                # explicit, the value is read with `id.value`
                ...

            @app("/:id")
            def example(id: str):
                # here id is directly a `str` because the annotation is
                # applied implicitly
                ...
        """
        value = await self.get_value(request)

        if value is None and self.default is not empty:
            return self.default

        if self.implicit:
            return value

        if self.root_required is False and value is None:
            # This is the case of:
            # Optional[BoundValue[T]]
            return None

        return self.handle(value)

    @abstractmethod
    async def get_value(self, request: Request) -> Optional[T]:
        """Gets a value from the given request object."""

    def __repr__(self):
        return f"<{self.__class__.__name__} " + f"{self.expected_type} at {id(self)}>"


def get_binder_by_type(bound_value_type: Type[BoundValue]) -> Type[Binder]:
    origin = bound_value_type.__dict__.get("__origin__")

    if origin and issubclass(origin, BoundValue):
        # In this case, it's a BoundValue of specified type
        bound_value_type = origin

    if bound_value_type in Binder.handlers:
        return Binder.handlers[bound_value_type]

    for cls in bound_value_type.__bases__:
        if cls in Binder.handlers:
            return Binder.handlers[cls]

    raise BinderNotRegisteredForValueType(bound_value_type)


class MissingBodyError(BadRequest):
    def __init__(self):
        super().__init__("Missing body payload")


class MissingParameterError(BadRequest):
    def __init__(self, name: str, source: str):
        super().__init__(f"Missing {source} parameter `{name}`")


class InvalidRequestBody(BadRequest):
    def __init__(self, description: str = "Invalid body payload"):
        super().__init__(description)


class MissingConverterError(Exception):
    def __init__(self, expected_type, binder_type):
        super().__init__(
            f"A default converter for type `{str(expected_type)}` "
            f"is not configured. "
            f"Please define a converter method for this binder "
            f"({binder_type.__name__})."
        )


class BodyBinder(Binder):
    _excluded_methods = {"GET", "HEAD", "TRACE"}

    def __init__(
        self,
        expected_type: T,
        name: str = "body",
        implicit: bool = False,
        required: bool = False,
        converter: Optional[Callable] = None,
    ):
        if not converter:

            def default_converter(data):
                return expected_type(**data)

            converter = default_converter
        super().__init__(expected_type, name, implicit, required, converter)

    @abstractmethod
    def matches_content_type(self, request: Request) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def read_data(self, request: Request) -> Any:
        raise NotImplementedError()

    async def get_value(self, request: Request) -> Optional[T]:
        if request.method not in self._excluded_methods and self.matches_content_type(
            request
        ):
            data = await self.read_data(request)

            if not data:
                raise MissingBodyError()

            return self.parse_value(data)

        if self.required:
            if self.default is not empty:
                # very unlikely: this is to support user defined default parameters
                return None

            if not request.has_body():
                raise MissingBodyError()

            raise InvalidRequestBody("Expected request content")

        return None

    def parse_value(self, data: dict) -> T:
        try:
            return self.converter(data)
        except TypeError as te:
            raise InvalidRequestBody(_generalize_init_type_error_message(te))
        except ValueError as ve:
            raise InvalidRequestBody(str(ve))


class JsonBinder(BodyBinder):
    """Extracts a model from JSON content"""

    handle = FromJson

    def matches_content_type(self, request: Request) -> bool:
        return request.declares_json()

    async def read_data(self, request: Request) -> Any:
        return await request.json()


class FormBinder(BodyBinder):
    """
    Extracts a model from form content, either
    application/x-www-form-urlencoded, or multipart/form-data.
    """

    handle = FromForm

    def matches_content_type(self, request: Request) -> bool:
        return request.declares_content_type(
            b"application/x-www-form-urlencoded"
        ) or request.declares_content_type(b"multipart/form-data")

    async def read_data(self, request: Request) -> Any:
        return await request.form()


def _default_bool_converter(value: str) -> bool:
    if value in {"1", "true"}:
        return True

    if value in {"0", "false"}:
        return False

    # bad request: expected a bool value, but
    # got something different that is not handled
    raise BadRequest(f"Expected a bool value for a parameter, but got {value}.")


def _default_bool_list_converter(values: Sequence[str]):
    return _default_bool_converter(values[0].lower()) if values else None


class SyncBinder(Binder):
    """
    Base binder class for values that can be read synchronously from requests
    with complete headers. Like route, query string and header parameters.
    """

    _simple_types = {int, float, bool}

    def __init__(
        self,
        expected_type: T = List[str],
        name: str = "",
        implicit: bool = False,
        required: bool = False,
        converter: Optional[Callable] = None,
    ):
        super().__init__(
            expected_type,
            name=name,
            implicit=implicit,
            required=required,
            converter=converter or self._get_default_converter(expected_type),
        )

    def __repr__(self):
        return f'<{self.__class__.__name__} "{self.parameter_name}" at {id(self)}>'

    def _get_default_converter_single(self, expected_type):
        if expected_type is str:
            return lambda value: unquote(value) if value else None

        if expected_type is bool:
            return _default_bool_converter

        if expected_type is bytes:
            return lambda value: value if value else None

        if expected_type in self._simple_types:
            return lambda value: expected_type(value) if value else None

        if expected_type is UUID:
            return lambda value: UUID(value)

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

        if expected_type is UUID:
            return lambda value: UUID(value[0]) if value else None

        if self._is_generic_iterable_annotation(expected_type) or expected_type in {
            list,
            set,
            tuple,
        }:
            return self._get_default_converter_for_iterable(expected_type)

        raise MissingConverterError(expected_type, self.__class__)

    def _get_type_for_generic_iterable(self, expected_type):
        if expected_type in {list, tuple, set}:
            return expected_type

        origin = expected_type.__origin__
        if origin in {list, tuple, set}:
            return origin
        # here we cannot make something perfect: if the user of the library
        # wants something better,
        # a converter should be specified when configuring binders; here the
        # code defaults to list
        # for all abstract types (typing.Sequence, Set, etc.) even though not perfect
        return list

    def _is_generic_iterable_annotation(self, param_type):
        return hasattr(param_type, "__origin__") and (
            param_type.__origin__ in {list, tuple, set}
            or issubclass(param_type.__origin__, IterableAbc)
        )

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

    async def get_value(self, request: Request) -> Optional[T]:
        # TODO: support get_raw_value returning None, to not instantiate lists
        # when a parameter is not present
        raw_value = self.get_raw_value(request)
        try:
            value = self.converter(raw_value)
        except (ValueError, BadRequest):
            raise BadRequest(
                f"Invalid value {raw_value} for parameter `{self.parameter_name}`; "
                f"expected a valid {self.expected_type.__name__}."
            )

        if self.default is not empty and (value is None or self._empty_iterable(value)):
            return None

        if value is None and self.required and self.root_required:
            raise MissingParameterError(self.parameter_name, self.source_name)

        if not self.required and self._empty_iterable(value):
            return None

        return value


class HeaderBinder(SyncBinder):
    handle = FromHeader

    @property
    def source_name(self) -> str:
        return "header"

    def get_raw_value(self, request: Request) -> Sequence[str]:
        return [
            header.decode("utf8")
            for header in request.get_headers(self.parameter_name.encode())
        ]


class QueryBinder(SyncBinder):
    handle = FromQuery

    @property
    def source_name(self) -> str:
        return "query"

    def get_raw_value(self, request: Request) -> Sequence[str]:
        return [value for value in request.query.get(self.parameter_name, [])]


class RouteBinder(SyncBinder):
    handle = FromRoute

    def __init__(
        self,
        expected_type: T = str,
        name: str = None,
        implicit: bool = False,
        required: bool = False,
        converter: Optional[Callable] = None,
    ):
        super().__init__(expected_type, name or "route", implicit, required, converter)

    def get_raw_value(self, request: Request) -> Sequence[str]:
        return [request.route_values.get(self.parameter_name, "")]

    @property
    def source_name(self) -> str:
        return "route"


class ServiceBinder(Binder):
    handle = FromServices

    def __init__(
        self,
        service: T,
        name: str = "",
        implicit: bool = False,
        services: Optional[Services] = None,
    ):
        super().__init__(service, name, implicit, False, None)
        self.services = services

    async def get_value(self, request: Request) -> Optional[T]:
        try:
            context = request.services_context  # type: ignore
        except AttributeError:
            # no support for scoped services
            # (across parameters and middlewares)
            context = None

        return self.services.get(self.expected_type, context)


class ControllerParameter(BoundValue[T]):
    pass


class ControllerBinder(ServiceBinder):
    """
    Binder used to activate an instance of Controller. This binder is applied
    automatically by the application
    object at startup, as type annotation, for handlers configured on classes
    inheriting `blacksheep.server.Controller`.

    If used manually, it causes several controllers to be instantiated and
    injected into request handlers.
    However, only the controller configured as `self` is taken into
    consideration for base route and callbacks.
    """

    handle = ControllerParameter

    async def get_value(self, request: Request) -> Optional[T]:
        return await super().get_value(request)


class RequestBinder(Binder):
    def __init__(self, implicit: bool = True):
        super().__init__(Request, implicit=implicit)

    async def get_value(self, request: Request) -> Optional[T]:
        return request


class RequestPropertyBinder(Binder):
    def __init__(self, property_name: str, expected_type: Type = Any):
        super().__init__(expected_type, property_name, implicit=True)
        self.property_name = property_name

    async def get_value(self, request: Request) -> Optional[T]:
        return getattr(request, self.property_name, None)


class IdentityBinder(Binder):
    handle = RequestUser

    async def get_value(self, request: Request) -> Optional[Identity]:
        return getattr(request, "identity", None)


class ExactBinder(Binder):
    def __init__(self, exact_object):
        super().__init__(object, implicit=True)
        self.exact_object = exact_object

    async def get_value(self, request: Request) -> Optional[T]:
        return self.exact_object


class ClientInfoBinder(Binder):
    handle = ClientInfo

    async def get_value(self, request: Request) -> Optional[T]:
        return tuple(request.scope["client"])


class ServerInfoBinder(Binder):
    handle = ServerInfo

    async def get_value(self, request: Request) -> Optional[T]:
        return tuple(request.scope["server"])
