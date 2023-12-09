import sys
from io import BytesIO
from typing import (
    Any,
    AsyncIterable,
    Callable,
    ClassVar,
    Optional,
    Sequence,
    Type,
    Union,
)

from blacksheep import Request, Response
from blacksheep.common.types import HeadersType, ParamsType
from blacksheep.server.responses import (
    ContentDispositionType,
    MessageType,
    accepted,
    bad_request,
    created,
    file,
    forbidden,
    html,
    json,
    moved_permanently,
    no_content,
    not_found,
    not_modified,
    permanent_redirect,
    pretty_json,
    redirect,
    see_other,
    status_code,
    temporary_redirect,
    text,
    unauthorized,
    view,
    view_async,
)
from blacksheep.server.routing import RouteFilter
from blacksheep.server.routing import RoutesRegistry as RoutesRegistry  # noqa
from blacksheep.server.routing import controllers_routes, normalize_filters
from blacksheep.utils import AnyStr, join_fragments

# singleton router used to store initial configuration,
# before the application starts
# this is used as *default* router for controllers, but it can be overridden
# - see for example tests in test_controllers
router = controllers_routes


head = router.head
get = router.get
post = router.post
put = router.put
patch = router.patch
delete = router.delete
trace = router.trace
options = router.options
connect = router.connect
route = router.route
ws = router.ws


def filters(
    *filters: RouteFilter,
    host: Optional[str] = None,
    headers: Optional[HeadersType] = None,
    params: Optional[ParamsType] = None,
):
    """
    Configures a set of filters for a decorated controller type.
    Filters are applied to all routes defined in the controller.

    ---
    Example: match a "/" route only if the request includes an header "X-Area: Special"

    ```py
    @filters(headers={"X-Area": "Special"})
    class Special(Controller):
        @get("/")
        def special(self):
            ...
    ```
    """

    def class_deco(cls: Type["Controller"]):
        cls._filters_ = normalize_filters(host, headers, params, list(*filters))
        return cls

    return class_deco


class CannotDetermineDefaultViewNameError(RuntimeError):
    def __init__(self):
        super().__init__(
            "Cannot determine the default view name to be used "
            "for the calling function. "
            "Modify your Controller `view()` function call to specify the name"
            " of the view to be used."
        )


class ControllerMeta(type):
    def __init__(cls, name, bases, attr_dict):
        super().__init__(name, bases, attr_dict)

        for value in attr_dict.values():
            if hasattr(value, "route_handler"):
                setattr(value, "controller_type", cls)


class Controller(metaclass=ControllerMeta):
    """Base class for all controllers."""

    _filters_: ClassVar[Sequence[RouteFilter]] = []

    @classmethod
    def route(cls) -> Optional[str]:
        """
        The base route to be used by all request handlers defined on a
        controller type.
        Override this class method in subclasses, to implement base routes.
        """
        return None

    async def on_request(self, request: Request):
        """
        Extensibility point: controllers support executing a function at each
        web request.
        This method is executed before model binding happens: it is possible
        to read values from the request:
        headers are immediately available, and the user can decide to wait for
        the body (e.g. await request.json()).

        Since controllers support dependency injection, it is possible to
        apply logic using dependent services,
        specified in the __init__ constructor.
        """

    async def on_response(self, response: Response):
        """
        Callback called on every response returned using controller's methods.
        """

    def status_code(self, status: int = 200, message: MessageType = None) -> Response:
        """
        Returns a plain response with given status, with optional message;
        sent as plain text or JSON.
        """
        return status_code(status, message)

    def ok(self, message: MessageType = None) -> Response:
        """
        Returns an HTTP 200 OK response, with optional message;
        sent as plain text or JSON.
        """
        return status_code(200, message)

    def created(self, value: Any = None, location: AnyStr = "") -> Response:
        """
        Returns an HTTP 201 Created response, to the given location and with
        optional JSON content.
        """
        return created(value, location)

    def accepted(self, message: MessageType = None) -> Response:
        """
        Returns an HTTP 202 Accepted response, with optional message;
        sent as plain text or JSON.
        """
        return accepted(message)

    def no_content(self) -> Response:
        """
        Returns an HTTP 204 No Content response.
        """
        return no_content()

    def html(self, data, status: int = 200) -> Response:
        """
        Returns a response with text/html content, and given status
        (default HTTP 200 OK).
        """
        return html(data, status)

    def json(self, data, status: int = 200) -> Response:
        """
        Returns a response with application/json content, and given status
        (default HTTP 200 OK).
        """
        return json(data, status)

    def pretty_json(self, data: Any, status: int = 200, indent: int = 4) -> Response:
        """
        Returns a response with indented application/json content,
        and given status (default HTTP 200 OK).
        """
        return pretty_json(data, status=status, indent=indent)

    def text(self, value: str, status: int = 200) -> Response:
        """
        Returns a response with text/plain content,
        and given status (default HTTP 200 OK).
        """
        return text(value, status)

    def moved_permanently(self, location: AnyStr) -> Response:
        """
        Returns an HTTP 301 Moved Permanently response, to the given location.
        """
        return moved_permanently(location)

    def redirect(self, location: AnyStr) -> Response:
        """
        Returns an HTTP 302 Found response (commonly called redirect), to the
        given location.
        """
        return redirect(location)

    def see_other(self, location: AnyStr) -> Response:
        """
        Returns an HTTP 303 See Other response, to the given location.
        """
        return see_other(location)

    def not_modified(self) -> Response:
        """
        Returns an HTTP 304 Not Modified response.
        """
        return not_modified()

    def temporary_redirect(self, location: AnyStr) -> Response:
        """
        Returns an HTTP 307 Temporary Redirect response, to the given location.
        """
        return temporary_redirect(location)

    def permanent_redirect(self, location: AnyStr) -> Response:
        """
        Returns an HTTP 308 Permanent Redirect response, to the given location.
        """
        return permanent_redirect(location)

    def bad_request(self, message: MessageType = None) -> Response:
        """
        Returns an HTTP 400 Bad Request response, with optional message;
        sent as plain text or JSON.
        """
        return bad_request(message)

    def unauthorized(self, message: MessageType = None) -> Response:
        """
        Returns an HTTP 401 Unauthorized response, with optional message;
        sent as plain text or JSON.
        """
        return unauthorized(message)

    def forbidden(self, message: MessageType = None) -> Response:
        """
        Returns an HTTP 403 Forbidden response, with optional message;
        sent as plain text or JSON.
        """
        return forbidden(message)

    def not_found(self, message: MessageType = None) -> Response:
        """
        Returns an HTTP 404 Not Found response, with optional message;
        sent as plain text or JSON.
        """
        return not_found(message)

    def get_default_view_name(self):
        """
        Returns the default view name, to be used by the calling function.
        """
        route_handler_name = self._get_route_handler_name()

        if route_handler_name is None:
            raise CannotDetermineDefaultViewNameError()
        return route_handler_name

    def file(
        self,
        value: Union[
            Callable[[], AsyncIterable[bytes]], str, bytes, bytearray, BytesIO
        ],
        content_type: str,
        *,
        file_name: Optional[str] = None,
        content_disposition: ContentDispositionType = ContentDispositionType.ATTACHMENT,
    ) -> Response:
        """
        Returns a binary file response with given content type and optional
        file name, for download (attachment)
        (default HTTP 200 OK). This method supports both call with bytes,
        or a generator yielding chunks.

        Remarks: this method does not handle cache, ETag and HTTP 304 Not Modified
        responses; when handling files it is recommended to handle cache, ETag and
        Not Modified, according to use case.
        """
        return file(
            value,
            content_type,
            content_disposition=content_disposition,
            file_name=file_name,
        )

    def _get_route_handler_name(self):
        """
        Returns the name of the closest route handler in the call stack.

        Note: this function is designed to improve user's experience when
        using the framework.
        It removes the need to explicit the name of the template when using
        the `view()` function.

        It uses sys._getframe, which is a CPython implementation detail and
        is not guaranteed to exist in all implementations of Python.
        https://docs.python.org/3/library/sys.html
        """
        i = 2
        # Note: no need to get the frame for this function and
        # the direct caller;
        while True:
            i += 1
            try:
                fn_meta = sys._getframe(i).f_code
            except AttributeError:
                # NB: if sys._getframe raises attribute error, it means
                # is not supported
                # by the used Python runtime; return None; which in turn
                # will cause an exception.
                return None
            except ValueError:
                break
            fn = getattr(self, fn_meta.co_name, None)

            if not fn:
                continue

            try:
                if fn.route_handler:
                    return fn_meta.co_name
            except AttributeError:
                pass
        return None

    @classmethod
    def class_name(cls) -> str:
        """
        Returns the class name to be used for conventional behavior.
        By default, it returns the lowercase class name.
        """
        return cls.__name__.lower()

    def full_view_name(self, name: str) -> str:
        """
        Returns the full view name for this controller.
        By default, this function concatenates the lowercase class name
        to the view name.

        Therefore, a Home(Controller) will look for templates inside
        /views/home/ folder.
        """
        return f"{self.class_name()}/{name}"

    def view(
        self, name: Optional[str] = None, model: Optional[Any] = None, **kwargs
    ) -> Response:
        """
        Returns a view rendered synchronously.

        :param name: name of the template (path to the template file,
            optionally without '.html' extension
        :param model: optional model, required to render the template.
        :return: a Response object
        """
        if name is None:
            name = self.get_default_view_name()

        return view(self.full_view_name(name), model, **kwargs)

    async def view_async(
        self, name: Optional[str] = None, model: Optional[Any] = None, **kwargs
    ) -> Response:
        """
        Returns a view rendered asynchronously.

        :param name: name of the template (path to the template file,
            optionally without '.html' extension
        :param model: optional model, required to render the template.
        :return: a Response object
        """
        if name is None:
            name = self.get_default_view_name()

        return await view_async(self.full_view_name(name), model, **kwargs)


class APIController(Controller):
    @classmethod
    def version(cls) -> Optional[str]:
        """
        The version of this api controller. If specified, it is included in
        the base route for this controller.

        Example:
            if version is 'v1', and base route 'cat'; all route handlers
            defined on the controller have prefix:
            /api/v1/cat

            if the class name ends with the version string, the suffix is
            automatically removed from routes, so:
            class CatV2; with version() -> "v2"; produces such routes:
            /api/v2/cat
            And not, ~/api/v2/catv2~!
        """
        return None

    @classmethod
    def route(cls) -> Optional[str]:
        cls_name = cls.class_name()
        cls_version = cls.version() or ""
        if cls_version and cls_name.endswith(cls_version.lower()):
            cls_name = cls_name[: -len(cls_version)]
        return join_fragments("api", cls_version, cls_name)
