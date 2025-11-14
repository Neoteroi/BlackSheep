"""
This module implements a feature inspired by "Model Binding" in ASP.NET web framework.
It provides a strategy to have request parameters read and injected into request
handlers. This feature is also useful to generate OpenAPI Documentation (Swagger)
automatically.

See:
    https://www.neoteroi.dev/blacksheep/binders/
"""

from abc import abstractmethod
from collections.abc import Iterable as IterableAbc
from functools import partial
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    ForwardRef,
    Generic,
    Sequence,
    Type,
    TypeVar,
)

from guardpost import Identity
from rodi import CannotResolveTypeException, ContainerProtocol

from blacksheep import Request
from blacksheep.contents import FormPart
from blacksheep.exceptions import BadRequest
from blacksheep.server.bindings.converters import class_converters, converters
from blacksheep.server.websocket import WebSocket
from blacksheep.url import URL

T = TypeVar("T")
TypeOrName = Type | str


empty = object()


class BindingException(Exception):
    pass


class BinderAlreadyDefinedException(BindingException):
    def __init__(self, class_name: str, overriding_class_name: str) -> None:
        super().__init__(
            f"There is already a binder defined for {class_name}. "
            f"The second type is: {overriding_class_name}"
        )


class NameAliasAlreadyDefinedException(BindingException):
    def __init__(self, alias: str, overriding_class_name: str) -> None:
        super().__init__(
            f"There is already a name alias defined for '{alias}', "
            f"the second type is: {overriding_class_name}"
        )
        self.alias = alias


class TypeAliasAlreadyDefinedException(BindingException):
    def __init__(self, alias: Any, overriding_class_name: str) -> None:
        super().__init__(
            f"There is already a type alias defined for '{alias.__name__}', "
            f"the second type is: {overriding_class_name}"
        )
        self.alias = alias


class BinderNotRegisteredForValueType(BindingException):
    def __init__(self, value_type: Type["BoundValue"]) -> None:
        super().__init__(
            f"There is no binder to handle: {value_type}. "
            f"To resolve, define a Binder class with `handle` class attribute "
            f"referencing {value_type}."
        )


class BinderMeta(type):
    handlers: dict[Type[Any], Type["Binder"]] = {}
    aliases: dict[Any, Callable[[ContainerProtocol], "Binder"]] = {}

    def __init__(cls, name, bases, attr_dict):
        super().__init__(name, bases, attr_dict)
        handle = getattr(cls, "handle", None)
        name_alias = getattr(cls, "name_alias", None)
        type_alias = getattr(cls, "type_alias", None)

        if name_alias:
            if name_alias in cls.aliases:
                raise NameAliasAlreadyDefinedException(name_alias, name)
            cls.aliases[name_alias] = cls.from_alias  # type: ignore

        if type_alias:
            if type_alias in cls.aliases:
                raise TypeAliasAlreadyDefinedException(type_alias, name)
            cls.aliases[type_alias] = cls.from_alias  # type: ignore

        if handle:
            if handle in cls.handlers:
                raise BinderAlreadyDefinedException(handle, name)
            cls.handlers[handle] = cls  # type: ignore


class BoundValue(Generic[T]):
    """Base class for parameters that are bound for a web request."""

    name: str | None = None

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
    """A parameter obtained from URL query parameters."""


class FromCookie(BoundValue[T]):
    """
    A parameter obtained from a cookie.
    """


class FromServices(BoundValue[T]):
    """
    A parameter obtained from configured application services.
    """


class FromJSON(BoundValue[T]):
    """
    A parameter obtained from JSON request body.
    If value type is `dict`, `typing.Dict`, or not specified, the deserialized JSON
    is returned without any cast.
    """

    default_value_type = dict


FromJson = FromJSON  # for backward compatibility


class FromText(BoundValue[str]):
    """
    A parameter obtained from the request body as plain text.
    """


class FromBytes(BoundValue[bytes]):
    """
    A parameter obtained from the request body as raw bytes.
    """


class FromForm(BoundValue[T]):
    """
    A parameter obtained from Form request body: either
    application/x-www-form-urlencoded or multipart/form-data.
    """

    default_value_type = dict


class FromFiles(BoundValue[list[FormPart]]):
    """
    A parameter obtained from multipart/form-data files.
    """


class FromRoute(BoundValue[T]):
    """
    A parameter obtained from URL path fragment.
    """


class ClientInfo(BoundValue[tuple[str, int]]):
    """
    Client ip and port information obtained from a request scope.
    """


class ServerInfo(BoundValue[tuple[str, int]]):
    """
    Server ip and port information obtained from a request scope.
    """


class RequestUser(BoundValue[Identity]):
    """
    Returns the identity of the user that initiated the web request.
    This value is obtained from the configured authentication strategy.
    """


class RequestURL(BoundValue[URL]):
    """
    Returns the URL of the request.
    """


class RequestMethod(BoundValue[str]):
    """
    Returns the HTTP Method of the request.
    """


def _implicit_default(obj: "Binder"):
    try:
        return issubclass(obj.handle, BoundValue)
    except (AttributeError, TypeError):
        return False


class Binder(metaclass=BinderMeta):  # type: ignore
    handle: ClassVar[Type[Any]]
    name_alias: ClassVar[str] = ""
    type_alias: ClassVar[Any] = None

    def __init__(
        self,
        expected_type: Any,
        name: str = "",
        implicit: bool = False,
        required: bool = True,
        converter: Callable | None = None,
    ):
        self._implicit = implicit or not _implicit_default(self)
        self.parameter_name = name
        self.expected_type = expected_type
        self.required = required
        self.root_required = True
        self.converter = converter
        self.default: Any = empty

    @classmethod
    def from_alias(cls, services: ContainerProtocol):
        return cls()  # type: ignore

    @property
    def implicit(self) -> bool:
        return self._implicit

    def get_type_for_generic_iterable(self, expected_type):
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

    def is_generic_iterable_annotation(self, param_type):
        return hasattr(param_type, "__origin__") and (
            param_type.__origin__ in {list, tuple, set}
            or self._issubclass(param_type.__origin__, IterableAbc)
        )

    @staticmethod
    def _issubclass(clstype, class_or_tuple) -> bool:
        try:
            return issubclass(clstype, class_or_tuple)
        except TypeError:
            return False

    def generic_iterable_annotation_item_type(self, param_type):
        try:
            item_type = param_type.__args__[0]
        except (IndexError, AttributeError):
            return str
        return item_type

    async def get_parameter(self, request: Request) -> Any:
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
        try:
            value = await self.get_value(request)
        except UnicodeDecodeError as decode_error:
            raise BadRequest(
                f"Unicode decode error. "
                f"Cannot decode the request content using: {decode_error.encoding}. "
                "Ensure the request content is encoded using the encoding declared in "
                "the Content-Type request header."
            )
        except ValueError as value_error:
            raise BadRequest("Invalid parameter.") from value_error

        if value is None and self.default is not empty:
            return self.default

        if self.implicit:
            return value

        if self.root_required is False and value is None:
            # This is the case of:
            # BoundValue[T | None]
            return None

        return self.handle(value)

    @abstractmethod
    async def get_value(self, request: Request) -> Any:
        """Gets a value from the given request object."""


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


def get_default_class_converter(expected_type):
    for converter in class_converters:
        if converter.can_convert(expected_type):
            return partial(converter.convert, expected_type=expected_type)

    def default_converter(data):
        if isinstance(data, dict):
            return expected_type(**data)
        else:
            # list, simple type
            return expected_type(data)

    return default_converter


class BodyBinder(Binder):
    _excluded_methods = {"GET", "HEAD", "TRACE"}

    def __init__(
        self,
        expected_type,
        name: str = "body",
        implicit: bool = False,
        required: bool = False,
        converter: Callable | None = None,
    ):
        super().__init__(expected_type, name, implicit, required, None)

        if not converter:
            converter = self.get_default_binder_for_body(expected_type)  # type: ignore
        self.converter = converter

    def _get_default_converter_single(self, expected_type):
        for converter in converters:
            if converter.can_convert(expected_type):
                return partial(converter.convert, expected_type=expected_type)
        return get_default_class_converter(expected_type)

    def _get_default_converter_for_iterable(self, expected_type):
        generic_type = self.get_type_for_generic_iterable(expected_type)
        item_type = self.generic_iterable_annotation_item_type(expected_type)

        if isinstance(item_type, ForwardRef):  # pragma: no cover
            from blacksheep.server.normalization import (
                UnsupportedForwardRefInSignatureError,
            )

            raise UnsupportedForwardRefInSignatureError(expected_type)

        item_converter = self._get_default_converter_single(item_type)

        def list_converter(values):
            if not isinstance(values, list):
                raise BadRequest("Invalid input: expected a list of objects.")

            return generic_type(item_converter(value) for value in values)

        return list_converter

    def get_default_binder_for_body(self, expected_type: Type):
        if self.is_generic_iterable_annotation(expected_type) or expected_type in {
            list,
            set,
            tuple,
        }:
            if expected_type is Dict or expected_type.__origin__ is dict:
                return lambda value: dict(**value)
            return self._get_default_converter_for_iterable(expected_type)

        return get_default_class_converter(expected_type)

    @property
    @abstractmethod
    def content_type(self) -> str:
        """Returns the content type related to this binder"""

    @abstractmethod
    def matches_content_type(self, request: Request) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def read_data(self, request: Request) -> Any:
        raise NotImplementedError()

    async def get_value(self, request: Request) -> T | None:
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

    def parse_value(self, data: dict):
        try:
            return self.converter(data)
        except TypeError as type_error:
            raise BadRequest(
                "Bad Request: invalid parameter in request payload."
            ) from type_error
        except ValueError as value_error:
            raise InvalidRequestBody(str(value_error)) from value_error


class JSONBinder(BodyBinder):
    """Extracts a model from JSON content"""

    handle = FromJSON

    @property
    def content_type(self) -> str:
        return "application/json"

    def matches_content_type(self, request: Request) -> bool:
        return request.declares_json()

    async def read_data(self, request: Request) -> Any:
        return await request.json()


JsonBinder = JSONBinder


class FormBinder(BodyBinder):
    """
    Extracts a model from form content, either
    application/x-www-form-urlencoded, or multipart/form-data.
    """

    handle = FromForm

    @property
    def content_type(self) -> str:
        return "multipart/form-data;application/x-www-form-urlencoded"

    def matches_content_type(self, request: Request) -> bool:
        return request.declares_content_type(
            b"application/x-www-form-urlencoded"
        ) or request.declares_content_type(b"multipart/form-data")

    async def read_data(self, request: Request) -> Any:
        return await request.form()


class TextBinder(BodyBinder):
    handle = FromText

    @property
    def content_type(self) -> str:
        return "text/plain"

    def matches_content_type(self, request: Request) -> bool:
        return True

    def parse_value(self, data: str):
        return data  # No need for parsing

    async def read_data(self, request: Request) -> Any:
        return await request.text()


class BytesBinder(Binder):
    handle = FromBytes

    async def get_value(self, request: Request) -> bytes | None:
        return await request.read()


class SyncBinder(Binder):
    """
    Base binder class for values that can be read synchronously from requests
    with complete headers. Like route, query string and header parameters.
    """

    def __init__(
        self,
        expected_type: Any = list[str],
        name: str = "",
        implicit: bool = False,
        required: bool = False,
        converter: Callable[[Sequence[str]], Any] | None = None,
    ):
        super().__init__(
            expected_type,
            name=name,
            implicit=implicit,
            required=required,
            converter=converter or self._get_converter(expected_type),
        )

    def _get_converter(self, expected_type) -> Callable[[Sequence[str]], Any]:
        if self.is_generic_iterable_annotation(expected_type) or expected_type in {
            list,
            set,
            tuple,
        }:
            return self._get_converter_for_iterable(expected_type)

        for converter in converters:
            if converter.can_convert(expected_type):
                return lambda values: converter.convert(
                    values[0] if values else None, expected_type
                )

        raise MissingConverterError(expected_type, self.__class__)

    def _get_converter_single(self, expected_type):
        for converter in converters:
            if converter.can_convert(expected_type):
                return partial(converter.convert, expected_type=expected_type)
        raise MissingConverterError(expected_type, self.__class__)

    def _get_converter_for_iterable(
        self, expected_type
    ) -> Callable[[Sequence[str]], Any]:
        generic_type = self.get_type_for_generic_iterable(expected_type)
        item_type = self.generic_iterable_annotation_item_type(expected_type)
        item_converter = self._get_converter_single(item_type)
        return lambda values: generic_type(item_converter(value) for value in values)

    @abstractmethod
    def get_raw_value(self, request: Request) -> Sequence[str]:
        """Reads a set of values from request information as strings."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Gets a name that describe the source of values for this SyncBinder."""

    _empty_iterables = [list(), set(), tuple()]

    def _empty_iterable(self, value):
        return value in self._empty_iterables

    async def get_value(self, request: Request) -> Any | None:
        raw_value = self.get_raw_value(request)
        try:
            value = self.converter(raw_value)
        except ValueError as converter_error:
            raise BadRequest(
                f"Invalid value {raw_value} for parameter `{self.parameter_name}`; "
                f"expected a valid {self.expected_type.__name__}."
            ) from converter_error

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


class CookieBinder(SyncBinder):
    handle = FromCookie

    @property
    def source_name(self) -> str:
        return "cookie"

    def get_raw_value(self, request: Request) -> Sequence[str]:
        cookie = request.cookies.get(self.parameter_name)
        if cookie:
            return [cookie]
        return []


class RouteBinder(SyncBinder):
    handle = FromRoute

    def __init__(
        self,
        expected_type: T = str,
        name: str | None = None,
        implicit: bool = False,
        required: bool = True,
        converter: Callable | None = None,
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
        service,
        name: str = "",
        implicit: bool = False,
        services: ContainerProtocol | None = None,
    ):
        super().__init__(service, name, implicit, False, None)
        self.services = services

    async def get_value(self, request: Request) -> Any:
        try:
            scope = request._di_scope  # type: ignore
        except AttributeError:
            # no support for scoped services
            # (across parameters and middlewares)
            scope = None
        assert self.services is not None
        try:
            return self.services.resolve(self.expected_type, scope)
        except CannotResolveTypeException:
            return None


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

    async def get_value(self, request: Request) -> T | None:
        return await super().get_value(request)


class RequestBinder(Binder):
    name_alias = "request"
    type_alias = Request

    def __init__(self, implicit: bool = True):
        super().__init__(Request, implicit=implicit)

    async def get_value(self, request: Request) -> Any:
        return request


class WebSocketBinder(Binder):
    name_alias = "websocket"
    type_alias = WebSocket

    def __init__(self, implicit: bool = True):
        super().__init__(WebSocket, implicit=implicit)

    async def get_value(self, websocket: WebSocket) -> WebSocket | None:
        return websocket


class IdentityBinder(Binder):
    handle = RequestUser

    async def get_value(self, request: Request) -> Identity | None:
        return getattr(request, "identity", None)


class ExactBinder(Binder):
    def __init__(self, exact_object):
        super().__init__(object, implicit=True)
        self.exact_object = exact_object

    async def get_value(self, request: Request) -> Any:
        return self.exact_object


class ServicesBinder(ExactBinder):
    name_alias = "services"

    @classmethod
    def from_alias(cls, services: ContainerProtocol) -> "ServicesBinder":
        return cls(services)


class ClientInfoBinder(Binder):
    handle = ClientInfo

    async def get_value(self, request: Request) -> tuple[str, int]:
        return tuple(request.scope["client"])


class ServerInfoBinder(Binder):
    handle = ServerInfo

    async def get_value(self, request: Request) -> tuple[str, int]:
        return tuple(request.scope["server"])


class RequestURLBinder(Binder):
    handle = RequestURL

    def __init__(self):
        super().__init__(URL, name="request url", implicit=False)

    async def get_value(self, request: Request) -> URL:
        return request.url


class RequestMethodBinder(Binder):
    handle = RequestMethod

    def __init__(self):
        super().__init__(str, name="request method", implicit=False)

    async def get_value(self, request: Request) -> str:
        return request.method


class FilesBinder(Binder):
    handle = FromFiles

    async def get_value(self, request: Request) -> list[FormPart]:
        return await request.files()
