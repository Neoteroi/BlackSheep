import sys
from typing import Any, Optional
from essentials import json as JSON
from blacksheep import Request, Response
from blacksheep.utils import BytesOrStr, join_fragments
from blacksheep.server.routing import RoutesRegistry
from blacksheep.server.responses import (json,
                                         pretty_json,
                                         text,
                                         status_code,
                                         permanent_redirect,
                                         temporary_redirect,
                                         moved_permanently,
                                         see_other,
                                         redirect,
                                         not_found,
                                         no_content,
                                         not_modified,
                                         forbidden,
                                         unauthorized,
                                         bad_request,
                                         accepted,
                                         created,
                                         MessageType)
from blacksheep.server.templating import view, view_async, Environment, MissingJinjaModuleError
# singleton router used to store initial configuration, before the application starts
# this is used as *default* router for controllers, but it can be overridden - see for example tests in test_controllers
router = RoutesRegistry()


head = router.head
get = router.get
post = router.post
put = router.put
patch = router.patch
delete = router.delete
trace = router.trace
options = router.options
connect = router.connect


if Environment is ...:
    TemplatesType = Any
else:
    TemplatesType = Optional[Environment]


class CannotDetermineDefaultViewNameError(RuntimeError):

    def __init__(self):
        super().__init__('Cannot determine the default view name to be used for the calling function. '
                         'Modify your Controller `view()` function call to specify the name of the view to be used.')


class ControllerMeta(type):

    def __init__(cls, name, bases, attr_dict):
        super().__init__(name, bases, attr_dict)

        for value in attr_dict.values():
            if hasattr(value, 'route_handler'):
                setattr(value, 'controller_type', cls)


class Controller(metaclass=ControllerMeta):
    """Base class for all controllers."""

    templates: TemplatesType = None
    """Templates environment: this class property is configured automatically by the application object at startup,
    because controllers activated by an application, need to use the same templating engine of the application.
    
    Templates are available only if the application uses templating - which is not necessary.
    """

    @classmethod
    def route(cls) -> Optional[str]:
        """
        The base route to be used by all request handlers defined on a controller type.
        Override this class method in subclasses, to implement base routes.
        """
        return None

    async def on_request(self, request: Request):
        """Extensibility point: controllers support executing a function at each web request.
        This method is executed before model binding happens: it is possible to read values from the request:
        headers are immediately available, and the user can decide to wait for the body (e.g. await request.json()).

        Since controllers support dependency injection, it is possible to apply logic using dependent services,
        specified in the __init__ constructor.
        """

    async def on_response(self, response: Response):
        """Callback called on every response returned using controller's methods."""

    def status_code(self, status: int = 200, message: MessageType = None) -> Response:
        """Returns a plain response with given status, with optional message; sent as plain text or JSON."""
        return status_code(status, message)

    def ok(self, message: MessageType = None) -> Response:
        """Returns an HTTP 200 OK response, with optional message; sent as plain text or JSON."""
        return status_code(200, message)

    def created(self, location: BytesOrStr, value: Any = None) -> Response:
        """Returns an HTTP 201 Created response, to the given location and with optional JSON content."""
        return created(location, value)

    def accepted(self, message: MessageType = None) -> Response:
        """Returns an HTTP 202 Accepted response, with optional message; sent as plain text or JSON."""
        return accepted(message)

    def no_content(self) -> Response:
        """Returns an HTTP 204 No Content response."""
        return no_content()

    def json(self, data, status: int = 200, dumps=JSON.dumps) -> Response:
        """Returns a response with application/json content, and given status (default HTTP 200 OK)."""
        return json(status, data, dumps)

    def pretty_json(self, data: Any, status: int = 200, dumps=JSON.dumps, indent: int = 4) -> Response:
        """Returns a response with indented application/json content, and given status (default HTTP 200 OK)."""
        return pretty_json(data, status, dumps, indent)

    def text(self, value: str, status: int = 200) -> Response:
        """Returns a response with text/plain content, and given status (default HTTP 200 OK)."""
        return text(value, status)

    def moved_permanently(self, location: BytesOrStr) -> Response:
        """Returns an HTTP 301 Moved Permanently response, to the given location"""
        return moved_permanently(location)

    def redirect(self, location: BytesOrStr) -> Response:
        """Returns an HTTP 302 Found response (commonly called redirect), to the given location"""
        return redirect(location)

    def see_other(self, location: BytesOrStr) -> Response:
        """Returns an HTTP 303 See Other response, to the given location."""
        return see_other(location)

    def not_modified(self) -> Response:
        """Returns an HTTP 304 Not Modified response."""
        return not_modified()

    def temporary_redirect(self, location: BytesOrStr) -> Response:
        """Returns an HTTP 307 Temporary Redirect response, to the given location."""
        return temporary_redirect(location)

    def permanent_redirect(self, location: BytesOrStr) -> Response:
        """Returns an HTTP 308 Permanent Redirect response, to the given location."""
        return permanent_redirect(location)

    def bad_request(self, message: MessageType = None) -> Response:
        """Returns an HTTP 400 Bad Request response, with optional message; sent as plain text or JSON."""
        return bad_request(message)

    def unauthorized(self, message: MessageType = None) -> Response:
        """Returns an HTTP 401 Unauthorized response, with optional message; sent as plain text or JSON."""
        return unauthorized(message)

    def forbidden(self, message: MessageType = None) -> Response:
        """Returns an HTTP 403 Forbidden response, with optional message; sent as plain text or JSON."""
        return forbidden(message)

    def not_found(self, message: MessageType = None) -> Response:
        """Returns an HTTP 404 Not Found response, with optional message; sent as plain text or JSON."""
        return not_found(message)

    def get_default_view_name(self):
        """Returns the default view name, to be used by the calling function."""
        route_handler_name = self._get_route_handler_name()

        if route_handler_name is None:
            raise CannotDetermineDefaultViewNameError()
        return route_handler_name

    def _get_route_handler_name(self):
        """Returns the name of the closest route handler in the call stack.

        Note: this function is designed to improve user's experience when using the framework.
        It removes the need to explicit the name of the template when using the `view()` function.

        It uses sys._getframe, which is a CPython implementation detail and is not guaranteed to be
        to exist in all implementations of Python.
        https://docs.python.org/3/library/sys.html
        """
        i = 2  # Note: no need to get the frame for this function and the direct caller;
        while True:
            i += 1
            try:
                fn_meta = sys._getframe(i).f_code
            except AttributeError:
                # NB: if sys._getframe raises attribute error, it means is not supported
                # by the used Python runtime; return None; which in turn will cause an exception.
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
    def class_name(cls):
        """Returns the class name to be used for conventional behavior.
        By default, it returns the lowercase class name.
        """
        return cls.__name__.lower()

    def full_view_name(self, name: str):
        """Returns the full view name for this controller.
        By default, this function concatenates the lowercase class name to the view name.

        Therefore, a Home(Controller) will look for templates inside /views/home/ folder.
        """
        return f'{self.class_name()}/{name}'

    def view(self,
             name: Optional[str] = None,
             model: Optional[Any] = None) -> Response:
        """
        Returns a view rendered synchronously.

        :param name: name of the template (path to the template file, optionally without '.html' extension
        :param model: optional model, required to render the template.
        :return: a Response object
        """
        if not name:
            name = self.get_default_view_name()

        if model:
            return view(self.templates, self.full_view_name(name), **model)
        return view(self.templates, self.full_view_name(name))

    async def view_async(self,
                         name: Optional[str] = None,
                         model: Optional[Any] = None) -> Response:
        """
        Returns a view rendered asynchronously.

        :param name: name of the template (path to the template file, optionally without '.html' extension
        :param model: optional model, required to render the template.
        :return: a Response object
        """
        if not name:
            name = self.get_default_view_name()

        if model:
            return await view_async(self.templates, self.full_view_name(name), **model)
        return await view_async(self.templates, self.full_view_name(name))


class ApiController(Controller):

    @classmethod
    def version(cls) -> Optional[str]:
        """
        The version of this api controller. If specified, it is included in the base route for this controller.

        Example:
            if version is 'v1', and base route 'cat'; all route handlers defined on the controller have prefix:
            /api/v1/cat

            if the class name ends with the version string, the suffix is automatically removed from routes, so:
            class CatV2; with version() -> "v2"; produces such routes:
            /api/v2/cat
            And not, ~/api/v2/catv2~!
        """
        return None

    @classmethod
    def route(cls) -> Optional[str]:
        cls_name = cls.class_name()
        cls_version = cls.version() or ''
        if cls_version and cls_name.endswith(cls_version.lower()):
            cls_name = cls_name[:-len(cls_version)]
        return join_fragments('api', cls_version, cls_name)


if Environment is ...:
    # Jinja2 is not a required dependency;
    # the Environment is configured as Ellipsis
    # Replace view functions with functions raising user-friendly exceptions
    setattr(Controller, 'view', MissingJinjaModuleError.replace_function())
    setattr(Controller, 'view_async', MissingJinjaModuleError.replace_function(True))
