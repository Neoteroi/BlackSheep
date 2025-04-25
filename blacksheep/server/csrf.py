import weakref
from typing import Optional, Sequence, Tuple

from itsdangerous import Serializer
from itsdangerous.exc import BadSignature

from blacksheep.baseapp import get_logger
from blacksheep.cookies import Cookie
from blacksheep.exceptions import Unauthorized
from blacksheep.messages import Request, Response
from blacksheep.server.application import Application
from blacksheep.server.dataprotection import generate_secret, get_serializer
from blacksheep.server.security import SecurityPolicyHandler
from blacksheep.settings.html import html_settings


class AntiForgeryTokenError(Unauthorized):
    def __init__(self, message: str):
        super().__init__(message)


class InvalidAntiForgeryTokenError(AntiForgeryTokenError):
    def __init__(self, message: str = "Invalid anti-forgery token"):
        super().__init__(message)


class MissingRequestContextError(TypeError):
    def __init__(self) -> None:
        super().__init__(
            "The request context is missing from the render call. Pass the request "
            "object to the context of the template."
        )


class ClickJackingProtection(SecurityPolicyHandler):
    """
    Class used to protect responses from click-jacking. This class is applied by default
    when using Anti-Forgery validation.
    """

    def protect(self, response: Response) -> None:
        """
        Applies response headers, to configure Content-Security-Policy and
        X-Frame-Options.
        """
        # for modern browsers
        response.add_header(b"Content-Security-Policy", b"frame-ancestors: 'self';")

        # for old browsers
        response.add_header(b"X-Frame-Options", b"SAMEORIGIN")


class AntiForgeryHandler:
    def __init__(
        self,
        cookie_name: str = "aftoken",
        form_name: str = "__RequestVerificationToken",
        header_name: str = "RequestVerificationToken",
        secret_keys: Optional[Sequence[str]] = None,
        serializer: Optional[Serializer] = None,
        security_handler: Optional[SecurityPolicyHandler] = None,
    ) -> None:
        """
        Creates a new instance of AntiForgeryHandler, that validates incoming
        requests that should provide an AntiForgery token.

        Parameters
        ----------
        cookie_name : str, optional
            The name of the cookie used to restore user's identity, by default
            "aftoken"
        header_name : str, optional
            The name of the header that can be used to send the control value, by
            default "RequestVerificationToken"
        form_name : str, optional
            The name of the form input that can be used to send the control value, by
            default "__RequestVerificationToken"
        secret_key : str, optional
            If specified, the key used by a default serializer (when no serializer is
            specified), by default None
        serializer : Optional[Serializer], optional
            If specified, controls the serializer used to sign and verify the values
            of cookies used for identities, by default None
        security_handler : Optional[SecurityPolicyHandler], optional
            Object used to protect responses that contain anti-forgery tokens. By
            default documents are protected against click-jacking allowing iframes only
            from the same site. Provide a custom object to control security rules.
        """
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.form_name = form_name
        self._serializer = serializer or get_serializer(secret_keys, "antiforgery")
        self.tokens = weakref.WeakKeyDictionary()
        self.reuse_tokens_among_requests = True
        self.security_policy = security_handler or ClickJackingProtection()
        self.logger = get_logger()

    VALIDATE_METHODS = set("PATCH POST PUT DELETE".split())

    @property
    def serializer(self) -> Serializer:
        return self._serializer

    async def __call__(self, request: Request, handler):
        if self._should_validate_route(request, handler):
            try:
                await self.validate_request(request)
            except AntiForgeryTokenError as token_error:
                return Response(401, [(b"Reason", str(token_error).encode())])

        response: Response = await handler(request)

        # are there tokens issued for the current request?
        if tokens := self.tokens.get(request):
            self.set_cookie(response, tokens[0])
            self.security_policy.protect(response)

        return response

    def _should_validate_route(self, request: Request, handler) -> bool:
        if _is_ignored_handler(handler):
            return False

        return self.should_validate_request(request)

    def should_validate_request(self, request: Request) -> bool:
        """
        Returns a value indicating whether the given request should be validated.
        Note that, even though according to the specification HTML form methods can
        only be GET or POST, this class by default validates requests also for other
        methods that can write / delete information: PATCH PUT DELETE.
        """
        return request.method in self.VALIDATE_METHODS

    async def validate_request(self, request: Request) -> None:
        token_in_cookie = self.read_cookie(request)
        token_in_second_parameter = await self.read_control_value(request)

        try:
            cookie_value = self.serializer.loads(token_in_cookie)
            control_value = self.serializer.loads(token_in_second_parameter)
        except BadSignature:
            raise InvalidAntiForgeryTokenError()

        if cookie_value != control_value[::-1]:
            self.logger.info("Invalid Anti-Forgery token: values do not match.")
            raise InvalidAntiForgeryTokenError()

    def set_cookie(self, response: Response, value: str, secure: bool = False) -> None:
        """
        Sets the cookie used to store the Anti-Forgery token. When validating requests,
        this token is read from the cookie and and matched with a second value that was
        transmitted in other ways (e.g. inside an input element).

        Parameters
        ----------
        data : Any
            Anything that can be serialized by an `itsdangerous.Serializer`, a
            dictionary in the most common scenario.
        response : Response
            The instance of blacksheep `Response` that will include the cookie for the
            client.
        secure : bool, optional
            Whether the set cookie should have secure flag, by default False
        """
        response.set_cookie(
            Cookie(
                self.cookie_name,
                value,
                domain=None,
                path="/",
                http_only=True,
                secure=secure,
            )
        )

    def read_cookie(self, request: Request) -> str:
        """
        Reads the value of the Anti-Forgery token stored in the cookie.
        This method raises an AntiForgeryTokenError if the cookie is missing.
        """
        cookie = request.get_cookie(self.cookie_name)

        if cookie is None:
            raise AntiForgeryTokenError("Missing anti-forgery token cookie")

        return cookie

    async def read_control_value(self, request: Request) -> str:
        """
        Reads the control-value token stored in a second location.
        By default this code tries to read the anti-forgery token from a header,
        """
        control_value = request.headers.get_first(self.header_name.encode())

        if control_value is not None:
            return control_value.decode()

        form_data = await request.form()

        if form_data is not None and self.form_name in form_data:
            value = form_data[self.form_name]
            if not isinstance(value, str):
                # the value can only be a list, this happens when more than one input
                # is configured (for example a mistake where {% af_input %} appears
                # more than once in the same form; use only the first value
                assert isinstance(value, list)
                return value[0]
            return value

        raise AntiForgeryTokenError("Missing anti-forgery token control value")

    def get_tokens(self, request: Request) -> Tuple[str, str]:
        """
        Gets a pair of anti-forgery tokens for the given request.
        If tokens were already generated for this request, it returns them, otherwise
        creates new tokens. By default, if tokens were already generated for the same
        client (i.e. if the web request contains a request cookie of a previous
        generation), it returns by default the same values to support the same page
        opened in multiple tabs of the browser, because generating a new cookie would
        invalidate the previous page.

        When Anti-Forgery tokens are generated for a web request,
        this class also configures a matching cookie in the generated response, to send
        one of the two values that will be used to validate subsequent web requests.
        """
        existing_cookie = request.cookies.get(self.cookie_name)

        if existing_cookie is not None and self.reuse_tokens_among_requests:
            # Do not generate new tokens for the same client. This is to support the
            # same web site being opened in multiple tabs of the same browser without
            # breaking any of those pages. This behavior can be disabled setting
            # reuse_tokens_among_requests to False.
            value_in_cookie = existing_cookie

            try:
                parsed_value = self.serializer.loads(value_in_cookie)
            except BadSignature:
                """Do nothing in this case, generate new tokens."""
            else:
                control_value = self._generate_control_token(parsed_value)

                # Note: in this case we don't set self.tokens[request] to not set a new
                # cookie on the Response object! We don't need it anyway.
                return (value_in_cookie, control_value)

        tokens = self.tokens.get(request)

        if tokens:
            return tokens
        else:
            tokens = self._generate_tokens()
            self.tokens[request] = tokens
            return tokens

    def _generate_control_token(self, cookie_value: str) -> str:
        control_value = self.serializer.dumps(cookie_value[::-1])
        assert isinstance(control_value, str)
        return control_value

    def _generate_tokens(self) -> Tuple[str, str]:
        """
        Generates two different tokens that can be matched later:
        * one is set as HTTPOnly cookie
        * one will be served in another way in HTML, for example as input element in
          forms
        """
        token = generate_secret(40)

        value_one = self.serializer.dumps(token)
        assert isinstance(value_one, str)

        value_two = self._generate_control_token(token)
        return (value_one, value_two)


_IGNORED_HANDLERS = {}


def _is_ignored_handler(handler) -> bool:
    """
    Returns a value indicating whether the given request handler is explicitly ignored
    for anti-forgery validation (for example to support cases that use alternative
    ways to authenticate the request, not vulnerable to CRSF).
    """
    if (
        handler in _IGNORED_HANDLERS
        or getattr(handler, "root_fn", None) in _IGNORED_HANDLERS
    ):
        return True

    return False


def ignore_anti_forgery(value: bool = True):
    """Optionally excludes a request handler from anti forgery validation."""

    def decorator(fn):
        _IGNORED_HANDLERS[fn] = value
        return fn

    return decorator


def use_anti_forgery(
    app: Application, handler: Optional[AntiForgeryHandler] = None
) -> AntiForgeryHandler:
    """
    Configures Anti-Forgery validation on the given application, to protect against
    Cross-Site Request Forgery (XSRF/CSRF) attacks.

    If the application is configured to use Jinja2, this function applies extensions to
    the templating environment to support rendering an anti-forgery token into the HTML
    of a web document.

    Example to render a hidden input:

        <form action="/user" method="post">
            {% af_input %}
            <input type="text" name="username" />
            <input type="submit" value="Submit" />
        </form>

    Example to render only a value:

        <script>
            EXAMPLE = {"token": "{% af_token %}"}
        </script>

    When an anti-forgery token is rendered in a view, the HTTP Response object receives
    also a cookie with a control value.
    """
    if handler is None:
        handler = AntiForgeryHandler()

    renderer = html_settings.renderer

    try:
        renderer.bind_antiforgery_handler(handler)
    except NotImplementedError:
        handler.logger.info(
            "The configured HTML renderer is not configured, or does not support "
            "anti-forgery extensions to render anti-forgery tokens in views."
        )

    app.middlewares.append(handler)

    return handler
