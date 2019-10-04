from typing import Any, Optional
from essentials import json as JSON
from blacksheep import Request, Response
from blacksheep.utils import BytesOrStr
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


class ControllerMeta(type):

    def __init__(cls, name, bases, attr_dict):
        super().__init__(name, bases, attr_dict)

        for value in attr_dict.values():
            if hasattr(value, 'route_handler'):
                setattr(value, 'controller_type', cls)


class Controller(metaclass=ControllerMeta):
    """Base class for all controllers."""

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
