# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.0] - 2025-05-10 :sun_behind_small_cloud:

> [!IMPORTANT]
>
> This release, like the previous one, includes some breaking changes to the
> public code API of certain classes, hence the bump in version from `2.2.0` to
> `2.3.0`. The breaking changes aim to improve the user experience (UX) when
> using `Controllers` and registering routes. In particular, they address
> issues [#511](https://github.com/Neoteroi/BlackSheep/issues/511) and
> [#540](https://github.com/Neoteroi/BlackSheep/issues/540).The scope of the
> breaking changes is relatively minor, as they affect built-in features that
> are *likely* not commonly modified: removes the `prepare_controllers` and the
> `get_controller_handler_pattern` from the `Application` class, transferring
> them to a dedicated `ControllersManager` class. Additionally, the `Router`
> class has been refactored to work consistently for request handlers defined
> as _functions_ and those defined as _Controllers' methods_.
>
> The _Router_ now allows registering all request handlers without evaluating
> them immediately, postponing duplicate checks, and introduces an
> `apply_routes` method to make routes effective upon application startup.
> This change is necessary to support using the same functions for both
> _functions_ and _methods_, addressing issue [#540](https://github.com/Neoteroi/BlackSheep/issues/540),
> improving UX, and eliminating potential confusion caused by having two
> sets of decorators (`get, post, put, etc.`) that behave differently. While
> the two sets of decorators are still maintained to minimize the impact of
> breaking changes, the framework now supports using them interchangeably.
>
> While breaking changes may cause inconvenience for some users, I believe the
> new features in this release represent a significant step forward.
> Now Controllers support routes inheritance! This is an important feature that
> was missing so far in the web framework.

- Fix [#511](https://github.com/Neoteroi/BlackSheep/issues/511). Add support
  for inheriting endpoints from parent controller classes, when subclassing
  controllers. Example:

```python
from blacksheep import Application
from blacksheep.server.controllers import Controller, abstract, get

app = Application()


@abstract()
class BaseController(Controller):
    @get("/hello-world")
    def index(self):
        # Note: the route /hello-world itself will not be registered in the router,
        # because this class is decorated with @abstract()
        return self.text(f"Hello, World! {self.__class__.__name__}")


class ControllerOne(BaseController):
    route = "/one"
    # /one/hello-world


class ControllerTwo(BaseController):
    route = "/two"
    # /two/hello-world

    @get("/specific-route")  # /two/specific-route
    def specific_route(self):
        return self.text("This is a specific route in ControllerTwo")
```

- Add a new `@abstract()` decorator that can be applied to controller classes to skip
  routes defined in them; so that only their subclasses will have the routes
  registered, prefixed by their own prefix).
- **BREAKING CHANGE**. Refactor the `Application` code to encapsulate in a
  dedicated class functions that prepare controllers' routes.
- **BREAKING CHANGE**. Refactor the `Router` class to handle consistently
  request handlers defined using _functions_ and controllers' class _methods_
  (refer to the note above for more information).
- Fix [#498](https://github.com/Neoteroi/BlackSheep/issues/498): Buffer reuse
  and race condition in `client.IncomingContent.stream()`, by @ohait.
- Fix [#365](https://github.com/Neoteroi/BlackSheep/issues/365), adding support
  for Pydantic's `@validate_call` and `@validate_arguments` and other wrappers
  applied to functions before they are configured as request handlers.
  Contribution by @aldem, who reported the issue and provided the solution.
- To better support `@validate_call`, configure automatically a default
  exception handler for `pydantic.ValidationError` when Pydantic is installed.
- Fix [#550](https://github.com/Neoteroi/BlackSheep/issues/550). Ensure that
  all generated `$ref` values contain only [allowed characters](https://swagger.io/docs/specification/v3_0/using-ref/).
- Fix [#484](https://github.com/Neoteroi/BlackSheep/issues/484). Improve the
  implementation of Server-Sent Events (SSE) to support sending data in any
  shape, and not only as JSON. Add a `TextServerSentEvent` class to send plain
  text to the client (this still escapes new lines!).
- Modify the `is_stopping` function to emit a warning instead of raising a
  `RuntimeError` if the env variable `APP_SIGNAL_HANDLER` is not set to a
  truthy value.
- Improve the error message of the `RouteDuplicate` class.
- Fix [#38](https://github.com/Neoteroi/BlackSheep-Docs/issues/38) for notations that
  are available since Python 3.9 (e.g. `list[str]`, `set[str]`, `tuple[str]`).
- Fix [a regression](https://github.com/Neoteroi/BlackSheep/issues/538#issuecomment-2867564293)
  introduced in `2.2.0` that would prevent custom `HTTPException`handlers from
  being used when the user configured a catch-all `Exception` handler
  (**this practice is not recommended; let the framework handle unhandled exceptions
  using `InternalServerError` exception handler**).
- Add a `Conflict` `HTTPException` to `blacksheep.exceptions` for `409`
  [response code](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/409).
- Improve the test code to make it less verbose.

## [2.2.0] - 2025-04-28 🎉

- Fix [#533](https://github.com/Neoteroi/BlackSheep/issues/533). **A feature
  that was requested several times in the past!** Add support for delegating
  the generation of OpenAPI schemas for types to external libraries and
  completely relies on schemas generated by **Pydantic** when working with
  `pydantic.BaseModel`.
- Add support for handling **Pydantic**
  [dataclasses](https://docs.pydantic.dev/latest/concepts/dataclasses/) when
  generating OpenAPI documentation.
- Add the possibility to control the `Serializer` class used to generate the
  _dict_ object of the OpenAPI Specification and to serialize it to **JSON**
  and **YAML**. This grants the user full control over the OpenAPI
  Specification, and enables more scenarios as users can modify the
  specification object comfortably and as they need. To use, pass a
  `serializer` parameter to the `OpenAPIHandler`'s constructor.
- Generates OpenAPI Specification with version `3.1.0` instead of `3.0.3`.
- Update `essentials-openapi` dependency to version `>=1.2.0`.
- Fix [#541](https://github.com/Neoteroi/BlackSheep/issues/541). Correct the
  type hint for the Jinja loader to use the abstract interface `BaseLoader`.
- Fix [#517](https://github.com/Neoteroi/BlackSheep/issues/517). Add support
  for any HTTP method when writing HTTP requests, not only for the most common
  methods.
- Fix [#529](https://github.com/Neoteroi/BlackSheep/issues/529). Add missing
  Jinja2 dependency in the `full` package.
- Fix type annotation in `messages.pyi`, by @bymoye.
- Add support for mapping types in OpenAPI Documentation, by @tyzhnenko.
- Improve `blacksheep/server/normalization.py` to bind any subclass of
  `Identity` using the `request.user` rather than just `User` and `Identity`
  exactly, by @bymoye.
- Add new UI provider for OpenAPI Documentation, for [Scalar
  UI](https://github.com/scalar/scalar), by @arthurbrenno and @bymoye.
- Correct the `ReDocUIProvider` to support a custom `favicon`.
- Fix [#538](https://github.com/Neoteroi/BlackSheep/issues/538). The
  `Application` object can now use both `Type` keys and `int` keys when
  applying the default _Not Found_ exception handler and the _Internal Server
  Error_ exception handler.
- **BREAKING CHANGE.** When an _unhandled_ exception occurs, user-defined
  exception handlers for _Internal Server Error_ status now always receive an
  instance of `InternalServerError` class, containing a reference to the source
  exception. Previously, user-defined internal server error handlers would
  **erroneously** receive any type of unhandled exception. If you defined your
  own exception handler for _InternalServerError_ or for _500_ status and you
  applied logic based on the type of the unhandled exception, update the code
  to read the source unhandled exception from `exc.source_error`.
- **BREAKING CHANGE.** Fix bug that would prevent `show_error_details` from
  working as intended when a user-defined `InternalServerError` exception
  handlers was defined. When `show_error_details` is enabled, any unhandled
  exception is handled by the code that produces the HTML document with error
  details and the stack trace of the error, even if the user configured an
  exception handler for internal server errors (using _500_ or
  _InternalServerError_ as keys). This is a breaking change if you made the
  mistake of running a production application with `show_error_details`
  enabled, and exception details are hidden using a custom _500_ exception
  handler.
- Improve type annotations for `get_files_to_serve` and
  `get_files_list_html_response`.
- The `TextBinder` is made a subclass of _BodyBinder_. This is correct and
  enables validation of handler signature and better generation of OpenAPI
  documentation. This binder was always about reading the request body as plain
  text.
- Modify `pyproject.toml` to specify `requires-python = ">=3.8"` instead of
  `requires-python = ">=3.7"`.
- Update the error message of the `AmbiguousMethodSignatureError` to make it
  clearer and offer a better user experience.
- Update the default message of the _InternalServerError_ class to be _Internal
  Server Error_ instead of _Internal server error._.

## [2.1.0] - 2025-03-23

- Remove support for Python 3.8, by @bymoye.
- Fix a bug in the `ClientSession`, happening when the server returns a response
  body without specifying `Content-Length` and without specifying a
  `Transfer-Encoding`.
- Fix a bug in the `ClientSession`, happening when a server closes the
  connection, and the response content is not set as completed.
- Add a default `User-Agent` to web requests sent using the `ClientSession`,
  the user agent is: `python-blacksheep/{__version__}`.
- Add an async method `raise_for_status` to the `Response` object, which raises
  an exception of type `FailedRequestError` if the response status is not in
  the range **200-299**. The method is asynchronous because in case of failure
  it waits for the response body to be downloaded, to include it in the raised
  exception.
- Add support for specifying a prefix for the `Router`, and for configuring a
  global prefix for all routes using the env variable `APP_ROUTE_PREFIX`.
  If specified, the prefix is applied to all routes registered in the
  application router. The prefix is used automatically by the
  `serve_files` method, the `get_absolute_url_to_path` method, and by the
  OpenAPI UI feature, to serve documentation to the correct path.
  This feature is useful when exposing applications behind proxies using
  path based routing, to maintain the same path between the proxy server and
  the BlackSheep application. This is an alternative approach to the one used
  by the `root_path` offered by `ASGI` (still supported in `BlackSheep`).
  ASGI `root_path` and route prefix in BlackSheep are alternative ways to
  address the same issue, and should not be used together.
- Improve the OpenAPI UI to support router prefixes, and fetching the
  specification file using relative links.
- Upgrade to `Cython` to `3.0.12` in the GitHub Workflow.
- Handle setuptools warning: _SetuptoolsDeprecationWarning: License classifiers are deprecated_.
- Improve `pyproject.toml` to use `tool.setuptools.packages.find`.
- Add the missing "utf8" encoding to the `request.path` property decode call.
- Add a middleware to handle automatic redirects from URLs that do not end with
  a "/" towards the same path with a trailing slash. This is useful for
  endpoints that serve HTML documents, to ensure that relative URLs in the
  response body are correctly resolved
  (`from blacksheep.server.redirects import get_trailing_slash_middleware`).
- Add a built-in strategy to handle startup errors and display an error page
  when an application fails during initialization, in
  `blacksheep.server.diagnostics.get_diagnostic_app`. Error details are not
  displayed by default, but can be displayed setting the environment variable
  `APP_SHOW_ERROR_DETAILS` to a value such as `1` or `true`.
- Use `asyncio_mode=auto` for `pytest` (remove `@pytest.mark.asyncio` decorators).
- Use `Python 3.12` to publish the package, in the GitHub Workflow.
- Modify the `Application` object to instantiate requests in a dedicated method
  `instantiate_request`. This is to better support code that modifies how
  incoming requests are created.
- Modify the `OpenAPIHandler` class to support specifying the list of `Server`
  objects in the constructor.
- Update `essentials-openapi` pinned version, by @stollero.
- Bump jinja2 from 3.1.4 to 3.1.6.
- Bump cryptography from 44.0.0 to 44.0.1.
- Remove `py` from the list of dependencies in `requirements.txt`.
- Correct some docstrings.

## [2.0.8] - 2025-01-25

- Add Python 3.13 to the build matrix and several maintenance fixes, by @waketzheng.
- Fix type error in `blacksheep/server/compression.py` `is_handled_encoding`;
  contributed by @bymoye and @ChenyangGao.
- Fix issue where the host is not the proxy address when there is a proxy by
  @ChenyangGao.
- Bump up action versions: actions/checkout@v1 -> v4, actions/setup-python@v4 -> v5
  by @waketzheng.
- Upgrade dependencies by @waketzheng.
- Handle the bytes type during build OpenAPI Specification, by @tyzhnenko.
- Exclude Accept, Content-type and Authorization header from OpenAPI docs, by @ticapix.
- Fix OpenAPI v3 issue (#492) by @mmangione.
- Set content-type header in TestSimulator (#502), by @tyzhnenko.
- Added support for WebSocket in TestClient, by @Randomneo.

## [2.0.7] - 2024-02-17 :tulip:

- Fixes bug [#38](https://github.com/Neoteroi/BlackSheep-Docs/issues/38),
  to support properly `list[T]` and `tuple[T]` when defining query string
  parameters. Reported by @ranggakd.
- Passes annotated origin type to build OpenAPI docs (#475), by @tyzhnenko.
- Fixes #481, disabling signal handling by default to avoid negative side
  effects. Handling signals is now opt-in and can be achieved using the env
  variable `APP_SIGNAL_HANDLER=1`. The `is_stopping` function is modified to
  work only when the option is enabled. Issue reported by @netanel-haber.
- Upgrades `black` version and format files accordingly.

## [2.0.6] - 2024-01-17 :kr: :heart:

- Adds built-in support for [Server-Sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events).
- Adds a function to detect when the server process is terminating because it
  received a `SIGINT` or a `SIGTERM` command
  (`from blacksheep.server.process import is_stopping`).
- Adds support for request handler normalization for methods defined as
  asynchronous generators. This feature is enabled by default only for
  ServerSentEvents, but can be configured for user defined types.
- Raises exception when the default router is used to register routes, but not
  associated to an application object. Fixes [#470](https://github.com/Neoteroi/BlackSheep/issues/470).

Refer to the [BlackSheep documentation](https://www.neoteroi.dev/blacksheep/server-sent-events/)
and to the [examples repository](https://github.com/Neoteroi/BlackSheep-Examples/tree/main/server-sent-events) for more information on server-sent events support.

## [2.0.5] - 2024-01-12 :pie:

- Fixes [#466](https://github.com/Neoteroi/BlackSheep/issues/466), regression
  introduced in 2.0.4 when using sub-routers, reported by @ruancan.

## [2.0.4] - 2023-12-31 :fireworks:

- Adds a `is_disconnected()` method to the `Request` class, similar to the one
  available in `Starlette`, which answers if the ASGI server published an
  `http.disconnected` message for a request.
  Feature requested by @netanel-haber in [#452](https://github.com/Neoteroi/BlackSheep/issues/452).
- Makes the `receive` callable of the `ASGI` request accessible to Python code,
  through the existing `ASGIContent` class. The `receive` property was already
  included in `contents.pyi` file and it was wrong to keep `receive` private
  for Cython code.
- Removes `consts.pxi` because it used a deprecated Cython feature.
- Upgrades the versions of Hypercorn and uvicorn for integration tests.
- Removes the unused "active" property defined in the `Response` class.
- Fixes #455, reported by @Klavionik. This error caused the WebSocket handler
  to erroneously return an instance of BlackSheep response to the underlying
  ASGI server, causing an error to be logged in the console.
- Updates type annotations in the `Application` class code to be more explicit
  about the fact that certain methods must return None (return in __call__ is
  used to interrupt code execution and not to return objects).
- Improves the normalization logic to not normalize the output for WebSocket
  requests (as ASGI servers do not allow controlling the response for WebSocket
  handshake requests).
- Improves the normalization logic to not normalize request handlers that are
  valid as they are, as asynchronous functions with a single parameter
  annotated as Request or WebSocket.
- Fixes #421 reported by @mohd-akram, causing handled exceptions to be logged
  like unhandled, when defining exception handlers using subclasses.
- Removes wrong type annotations in two functions in `blacksheep.utils`.

## [2.0.3] - 2023-12-18 :gift:

- Fixes #450, about missing `Access-Control-Allow-Credentials` response header
  in CORS responses after successful pre-flight requests. Reported by @waweber

## [2.0.2] - 2023-12-15 :christmas_tree:

- Upgrades default SwaggerUI files to version 5, by @sinisaos
- Fixes #427, handling WebSocket errors according to ASGI specification, by @Klavionik
- Adds support for custom files URLs for ReDoc and Swagger UI, by @joshua-auchincloss

## [2.0.1] - 2023-12-09 :mount_fuji:

- Fixes #441 causing the `refresh_token` endpoint for OpenID Connect
  integrations to not work when authentication is required by default.
- Fixes #443, raising a detailed exception when more than one application is
  sharing the same instance of `Router`
- Fixes #438 and #436, restoring support for `uvicorn` used programmatically
  and reloading the application object more than once in the same process.

## [2.0.0] - 2023-11-18 :mage_man:

- Releases v2 as stable.
- Removes the `route` method from the `Application` class, and move it to the
  `Router` class to be consistent with other methods to register request
  handlers.
- Removes `ClientConnectionPool` and `ClientConnectionPools` aliases.

## [2.0a12] - 2023-11-17 :fallen_leaf:

- Adds support for Python 3.12, by @bymoye
- Replaces `pkg_resources` with `importlib.resources` for all supported Python
  versions except for `3.8`.
- Runs tests against Pydantic `2.4.2` instead of Pydantic `2.0` to check
  support for Pydantic v2.
- Upgrades dependencies.
- Adds `.webp` and `.webm` to the list of extensions of files that are served
  by default.

## [2.0a11] - 2023-09-19 :warning:

- Resolves bug in `2.0a10` caused by incompatibility issue with `Cython 3`.
- Pins `Cython` to `3.0.2` in the build job.

## [2.0a10] - 2023-08-21 :broccoli:

- Add support for `.jinja` extension by @thearchitector.
- Makes the `.jinja` extension default for Jinja templates.

## [2.0a9] - 2023-07-14

- Fixes bug #394, causing the `Content` max body size to be 2147483647.
  (C int max value). Reported and fixed by @thomafred.

## [2.0a8] - 2023-07-02

- Add support for `StreamedContent` with specific content length; fixing
  [#374](https://github.com/Neoteroi/BlackSheep/issues/374) both on the client
  and the server side.
- Fix [#373](https://github.com/Neoteroi/BlackSheep/issues/373), about missing
  closing ASGI message when an async generator does not yield a closing empty
  bytes sequence (`b""`).
- Make version dynamic in `pyproject.toml`, simplifying how the version can be
  queried at runtime (see [#362](https://github.com/Neoteroi/BlackSheep/issues/362)).
- Fix [#372](https://github.com/Neoteroi/BlackSheep/issues/372). Use the ASGI
  scope `root_path` when possible, as `base_path`.
- Fix [#371](https://github.com/Neoteroi/BlackSheep/issues/371). Returns status
  403 Forbidden when the user is authenticated but not authorized to perform an
  action.
- Fixes `TypeError` when writing a request without host header.
- Add support for `Pydantic` `v2`: meaning feature parity with support for
  Pydantic v1 (generating OpenAPI Documentation).
- Add support for `Union` types in sub-properties of request handlers input and
  output types, for generating OpenAPI Documentation, both using simple classes
  and Pydantic [#389](https://github.com/Neoteroi/BlackSheep/issues/389)

## [2.0a7] - 2023-05-31 :corn:

- Fixes bug in CORS handling when [multiple origins are
  allowed](https://github.com/Neoteroi/BlackSheep/issues/364).
- Adds a `Vary: Origin` response header for CORS requests when the value of
  `Access-Control-Allow-Origin` header is a specific URL.
- Adds algorithms parameter to JWTBearerAuthentication constructor, by @tyzhnenko.
- Improves the code API to define security definitions in OpenAPI docs, by @tyzhnenko.
- Applies a correction to the auto-import function for routes and controllers.

## [2.0a6] - 2023-04-28 :crown:

- Adds support for automatic import of modules defined under `controllers` and
  `routes` packages, relatively to where the `Application` class is
  instantiated. Fix #334.
- Adds a `GzipMiddleware` that can be used to enable `gzip` compression, using
  the built-in module. Contributed by @tyzhnenko :sparkles:
- Improves how tags are generated for OpenAPI Documentation: adds the
  possibility to document tags explicitly and control their order, otherwise
  sorts them alphabetically by default, when using controllers or specifying
  tags for routes. Contributed by @tyzhnenko :sparkles:
- Adds a strategy to control features depending on application environment:
  `is_development`, `is_production` depending on `APP_ENV` environment
  variable. For more information, see [_Defining application
  environment_](https://www.neoteroi.dev/blacksheep/settings/#defining-application-environment).
- Makes the client `ConnectionPools` a context manager, its `__exit__` method
  closes all its `TCP-IP` connections.
- Improves exception handling so it is possible to specify how specific types
  of `HTTPException` must be handled (#342).
- Improves the error message when a list of objects if expected for an incoming
  request body, and a non-list value is received (#341).
- Replaces `chardet` and `cchardet` with `charset-normalizer`. Contributed by
  @mementum.
- Upgrades all dependencies.
- Adopts `pyproject.toml`.

## [2.0a5] - 2023-04-02 :fish:

- Adds support for user defined filters for server routes (`RouteFilter` class).
- Adds built-in support for routing based on request headers.
- Adds built-in support for routing based on request query parameters.
- Adds built-in support for routing based on host header value.
- Adds a `query.setter` to the `Request` class, to set queries using
  `dict[str, str | sequence[str]]` as input.
- The functions registered to application events don't need anymore to define
  the `app` argument (they can be functions without any argument).
- Adds `Cache-Control: no-cache, no-store' to all responses generated for the
  OpenID Connect flow.

## [2.0a4] - 2023-03-19 :flamingo:

- Adds `@app.lifespan` to support registering objects that must be initialized
  at application start, and disposed at application shutdown.
  The solution supports registering as many objects as desired.
- Adds features to handle `cache-control` response headers: a decorator for
  request handlers and a middleware to set a default value for all `GET`
  requests resulting in responses with status `200`.
- Adds features to control `cache-control` header for the default document
  (e.g. `index.html`) when serving static files;
  see [issue 297](https://github.com/Neoteroi/BlackSheep/issues/297).
- Fixes bug in `sessions` that prevented updating the session data when using
  the `set` and `__delitem__` methods;
  [scottrutherford](https://github.com/scottrutherford)'s contribution.

`@app.lifespan` example:

```python
from blacksheep import Application
from blacksheep.client.session import ClientSession

app = Application()


@app.lifespan
async def register_http_client():
    async with ClientSession() as client:
        print("HTTP client created and registered as singleton")
        app.services.register(ClientSession, instance=client)
        yield

    print("HTTP client disposed")


@app.router.get("/")
async def home(http_client: ClientSession):
    print(http_client)
    return {"ok": True, "client_instance_id": id(http_client)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=44777, log_level="debug", lifespan="on")
```

## [2.0a3] - 2023-03-12 🥐

- Refactors the `ClientSession` to own by default a connections pool, if none
  is specified for it. The connections pool is automatically disposed when the
  client is exited, if it was created for the client.
- Makes the `ClientSession` more user friendly, supporting headers defined as
  `dict[str, str]` or `list[tuple[str, str]]`.
- Improves the type annotations of the `ClientSession`.
- Corrects a bug in the `ClientSession` that would cause a task lock when the
  connection is lost while downloading files.
- Corrects a bug in the `ClientSession` causing `set-cookie` headers to not be
  properly handled during redirects.
- Renames the client connection pool classes to remove the prefix "Client".
- Corrects bug of the `Request` class that would prevent setting `url` using a
  string instead of an instance of `URL`.
- Corrects bug of the `Request` class that prevented the `host` property from
  working properly after updating `url` (causing `follow_redirects` to not work
  properly in `ClientSession`.
- Upgrades the `essentials-openapi` dependency, fixing [#316](https://github.com/Neoteroi/BlackSheep/issues/316).
- Corrects the `Request` class to not generate more than one `Cookie` header
  when multiple cookies are set, to [respect the specification](https://www.rfc-editor.org/rfc/rfc6265#section-5.4).

## [2.0a2] - 2023-03-05 :shield:

- Refactors the classes for OpenID Connect integration to support alternative
  ways to share tokens with clients, and JWT Bearer token authentication out
  of the box, in alternative to cookie based authentication.
- It adds built-in support for storing tokens (`id_token`, `access_token`, and
  `refresh_token`) using the HTML5 Storage API (supportin `localStorage` and
  `sessionStorage`). Refresh tokens, if present, are automatically protected to
  prevent leaking. See [the OIDC
  examples](https://github.com/Neoteroi/BlackSheep-Examples/tree/main/oidc) for
  more information.
- Renames `blacksheep.server.authentication.oidc.BaseTokensStore` to `TokensStore`.
- Removes the `tokens_store` parameter from the `use_openid_connect` method;
  it is still available as optional parameter of the two built-in classes used
  to handle tokens.
- Replaces `request.identity` with `request.user`. The property `identity` is
  still kept for backward compatibility, but it will be removed in `v3`.
- Removes 'HtmlContent' and 'JsonContent' that were kept as alternative names
  for `HTMLContent` and `JSONContent`.

## [2.0a1] - 2023-02-17 :heart:

- Improves how custom binders can be defined, reducing code verbosity for
  custom types. This is an important feature to implement common validation of
  common parameters across multiple endpoints.
- Adds support for binder types defining OpenAPI Specification for their
  parameters.
- Fixes bug #305 (`ClientSession ssl=False` not working as intended).

## [2.0a0] - 2023-01-08 :hourglass_flowing_sand:

- Renames the `plugins` namespace to `settings`.
- Upgrades `rodi` to v2, which includes improvements.
- Adds support for alternative implementation of containers for dependency
  injection, using the new `ContainerProtocol` in `rodi`.
- Upgrades `guardpost` to v1, which includes support for
  dependency injection in authentication handlers and authorization requirements.
- Adds support for Binders instantiated using dependency injection. However,
  binders are still instantiated once per request handler and are still
  singletons.
- Adds a method to make the `Request` object accessible through dependency
  injection (`register_http_context`). This is not a recommended practice,
  but it can be desired in some circumstances.
- Removes the direct dependency on `Jinja2` and adds support for alternative
  ways to achieve Server Side Rendering (SSR) of HTML; however, `Jinja2` is still
  the default library if the user doesn´t specify how HTML should be rendered.
- Adds options to control `Jinja2` settings through environment variables.
- Removes the deprecated `ServeFilesOptions` class.

## [1.2.8] - 2022-10-27 :snake:
- Upgrades pinned dependencies to support Python 3.11
- Drops active support for Python 3.7 (it is not tested anymore in CI pipelines)
- Fixes #271 and #274

## [1.2.7] - 2022-05-15 :gemini:
- Fixes #257 (bug causing OpenAPI Documentation handler to fail on app start
  when using PEP 585)
- Adds support for PEP 604 (T | None)
- Corrects a bug related to handling of optional parameters and `nullable` value
  in schemas generated for OpenAPI Documentation V3
- Corrects the capitalization of "ApiController" to be "APIController", still
  keeping the first name for backward compatibility
- Verifies in tests that `Annotated` is supported by BlackSheep

## [1.2.6] - 2022-04-28 :candle:
- Fixes #248, #253
- Improves support for pydantic (fixes #249)
- Adds support for configuring the Internal Server Error 500 handler for
  unhandled exceptions (see #247)
- Adds built-in HSTS middleware to configure Strict-Transport-Security

## [1.2.5] - 2022-03-12 :dove:
- Improves WebSocket to handle built-in exception types: Unauthorized, HTTPException
- Adds built-in support for [Anti Forgery validation](https://www.neoteroi.dev/blacksheep/anti-request-forgery) to protect against Cross-Site Request Forgery (XSRF/CSRF) attacks
- Modifies the Request and Response classes to support weak references
- Adds the possibility to use `**kwargs` in view functions, returning HTML built
  using Jinja2
- Adds support for automatic handling of child application events when BlackSheep
  applications are mounted into a parent BlackSheep application
- Adds support for OpenAPI Documentation generated for children BlackSheep apps,
  when using mounts
- Corrects bugs that prevented mounted routes to work recursively in descendants
- Updates dependencies

## [1.2.4] - 2022-02-13 :cat:
- Modifies the `WebSocket` class to support built-in binders
- Re-exports the most common types from the `blacksheep` module to reduce
  the verbosity of import statements

## [1.2.3] - 2022-02-06 :cat2:
- Adds support for [WebSocket](https://www.neoteroi.dev/blacksheep/websocket/)

## [1.2.2] - 2021-12-03 :gift:
- Fixes wrong mime type in OpenAPI Documentation for the `form` binder (#212)
- Adds `OpenAPIEvents` to the class handling the generation of OpenAPI Documentation
- Updates default environment variable prefix for app secrets to be `APP_SECRET`
  instead of `APPSECRET` (also accepts the value without underscore for backward
  compatibility)
- Adds missing server import to `blacksheep/__init__.pyi`

## [1.2.1] - 2021-11-15 :shield:
- Adds built-in support for `JWT` bearer authentication, and validation
  of `JWTs` issued by identity providers implementing **OpenID Connect (OIDC)**
  discovery `/.well-known/openid-configuration` (more in general, for JWTs
  signed using asymmetric encryption and verified using public RSA keys)
- Adds built-in support for **OpenID Connect (OIDC)** **Authorization Code Grant**
  and **Hybrid** flows, which can be used to integrate with `OAuth` applications
- Adds built-in handling of `X-Forwarded` and `Forwarded` headers with
  validation, including handling of trusted hosts
- Adds a `TrustedHostsMiddleware` that can be used to validate hosts
- Adds methods to obtain the request full URL, handling forward headers
- Adds an extensibility point that enables sorting of middlewares before they
  are applied on the application
- Fixes #199
- Downgrades `httptools` dependency to version `>=0.2,<0.4`
- Adds some improvements to the `testing` module
- Upgrades `itsdangerous` to version `~=2.0.1`
- Deprecates the `encryptor` option for sessions, applies `itsdangerous`
  `Serializer` by default

## [1.2.0] - 2021-10-24 📦
- Includes `Python 3.10` in the CI/CD matrix
- Includes `Python 3.10` wheel in the distribution package
- Removes `orjson` development dependency when running tests
- Fixes a bug happening in the code generating OpenAPI Documentation when
  running `Python 3.10`

## [1.1.0] - 2021-10-23 👶
- Upgrades `httptools` dependency to version `0.3.0`
- Upgrades `python-dateutil` dependency to version `2.8.2`
- Upgrades `Jinja2` dependency to version `3.0.2`
- Modifies `setup.py` dependencies to be less strict (`~=` instead of `==`)

## [1.0.9] - 2021-07-14 🇮🇹
- Adds support for application mounts (see [discussion #160](https://github.com/Neoteroi/BlackSheep/discussions/160))
- Applies sorting of imports using `isort`, enforces linters in the CI pipeline
  with both `black` and `isort`
- Adds support for application events defined using decorators: `@app.on_start`,
  `@app.on_stop`
- Upgrades `Jinja2` dependency to version `3.0.1`
- Adds support to configure JSON serializer and deserializer globally
  for the web framework (#138), thus adding support for custom logic happening
  upong JSON serialization and deserialization, and also for different
  libraries like `orjson`, to handle JSON serialization and deserialization

## [1.0.8] - 2021-06-19 :droplet:
- Corrects a bug forcing `camelCase` on examples objects handled as dataclasses
  (issue [#173](https://github.com/Neoteroi/BlackSheep/issues/173)), updating
  the dependency on `essentials-openapi` to [v1.0.4](https://github.com/Neoteroi/essentials-openapi/blob/v0.1.4/CHANGELOG.md#014---2021-06-19-droplet)
- Corrects a bug causing duplicate components definitions in generated OpenAPI
  documentation, when handling `Optional[T]`
- Minor corrections to the `TestClient` class: HTTP HEAD, OPTIONS, and TRACE
  should not allow request content body, therefore the corresponding methods
  are updated to not support a `content` parameter
- Automatically generates `404` response documentation when a request handler
  defines an `Optional[T]` return type (this happens only when the user doesn't
  specify the documentation for an endpoint)

## [1.0.7] - 2021-06-11 🍉
- Adds a `TestClient` class that simplifies testing of applications
- Fixes bug [#156](https://github.com/Neoteroi/BlackSheep/issues/156),
  preventing route parameters to work when the user doesn't follow Python
  naming conventions
- Adds support for automatic generation of OpenAPI Documentation for `Generic`
  types
- Improves the generation of OpenAPI Documentation for `pydantic` types and to
  support more object types (fixes [#167](https://github.com/Neoteroi/BlackSheep/issues/167))
- Ensures that request body is parsed as JSON only if the content type contains
  the "json" substring

## [1.0.6] - 2021-05-30 :birthday:
- Fixes bug [#153](https://github.com/Neoteroi/BlackSheep/issues/153),
  reintroducing compatibility with [Hypercorn](https://pgjones.gitlab.io/hypercorn/index.html)
- Fixes a bug that made links generated for the discovery of static files not
  working (double leading "/" in `href`)
- Provides a way to normalize request handlers' response type when using custom
  decorators (issue #135)
- Adds support for testing Hypercorn and tests Hypercorn in GitHub Actions

## [1.0.5] - 2021-05-11 :crown:
- Corrects details for documenting docstring parameters; i.e. supports
  documenting `request_body` in the same way a s `parameters`, and properly
  ignoring parameters handled by dependency injection and other kinds of bound
  values that should not appera in OpenAPI Documentation.

## [1.0.4] - 2021-05-09 :crown:
- Adds the `Application.exception_handler` decorator which registers exception
  handler functions
- Adds support for documenting parameters' descriptions, with support for
  various `docstring` formats: `Epytext`, `reStructuredText`, `Google`,
  `Numpydoc` (fixes #124, see discussion
  [#123](https://github.com/Neoteroi/BlackSheep/discussions/123))
- Corrects stubs for cookies: `Response.unset_cookie`, and `Cookie` same site
  annotation
- Updates `essentials-openapi` dependency to its next minor version, thus
  upgrading `PyYAML` dependency to `5.4.1`
- Updates `httptools` dependency to version `0.2.0`
- Throws exception for cookies whose value exceeds the standard length (#96)

## [1.0.3] - 2021-04-24 :cookie:
- Adds support for Python 3.10 and PEP 563 (however, it works with `httptools`
  built from its current default branch, because the version of `httptools`
  currently in `PyPi` does not support Python 3.10)
- Fixes bug [#109](https://github.com/Neoteroi/BlackSheep/issues/109) (client
  not handling properly various formats for Cookie time representations)
- Improves a detail in the client session URL handling (doesn't cause exception
  for an empty string URL, defaults to "/")

## [1.0.2] - 2021-04-15 :rocket:
- Applies normalization to return types, when a request handler doesn't return
  an instance of `Response` class, defaulting to a `Response` with JSON body
  in most cases, and plain/text if the request handler returns a string;
  this enables more accurate _automatic_ generation of OpenAPI Documentation
  (see #100)
- Renames `HtmlContent`, `JsonContent`, `FromJson`, and `JsonBinder` classes to
  respect Python naming conventions (to `HTMLContent`, `JSONContent`,
  `FromJSON`, and `JSONBinder`); however, the previous names are kept as
  aliases, for backward compatibility
- Corrects a detail in the `JSONContent` class default dumps function
- Adds support for logging the route pattern for each web request (for logging
  purposes, see issue [#99](https://github.com/Neoteroi/BlackSheep/issues/99))
- Adds support for OpenAPI Docs anonymous access, when a default authentication
  policy requires an authenticated user
- Adds support for [`ReDoc`](https://github.com/Redocly/redoc) UI (see [the
  documentation](https://www.neoteroi.dev/blacksheep/openapi/))

## [1.0.1] - 2021-03-20 :cake:
- Adds a built-in implementation for [sessions](https://www.neoteroi.dev/blacksheep/sessions/)
- Corrects a bug in cookie handling (#37!)
- Fixes #90, i.e. missing CORS response headers when exception are used to
  control the request handler's flow
- Corrects URLs in the README to point to [Neoteroi](https://github.com/Neoteroi),
  also for [Codecov](https://app.codecov.io/gh/Neoteroi/BlackSheep)

## [1.0.0] - 2021-02-25 :hatching_chick:
- Upgrades dependencies
- Improves the internal server error page and the code handling it
- Marks the web framework as stable

## [0.3.2] - 2021-01-24 :grapes:
- Logs handled and unhandled exceptions (fixes: #75)
- Adds support for [Flask Variable Rules syntax](https://flask.palletsprojects.com/en/1.1.x/quickstart/?highlight=routing#variable-rules) (ref. #76) and more granular control on the
  route parameters' patterns when matching web requests
- Adds the missing `html` method to the `Controller` class (#77) - thanks to
  [skivis](https://github.com/Neoteroi/BlackSheep/commits?author=skivis)!
- Deprecates the `ServeFilesOptions` class and reduces verbosity of the
  `Application.serve_files` method (#71)

## [0.3.1] - 2020-12-27 🎄
- Implements an abstraction layer to [handle CORS](https://www.neoteroi.dev/blacksheep/cors/)
- Improves the code API to handle [response cookies](https://www.neoteroi.dev/blacksheep/responses/#setting-cookies)
- Improves the default handling of authorization for request handlers (#69)
- Adds more binders: `FromText`, `FromBytes`, `RequestMethod`, `RequestURL`
- Improves `FromJSON` binder to support returning the dictionary after JSON deserialization
- Improves the default bad request response for invalid dataclass
- Adds two more features to the OpenAPI Documentation:
- - support defining common responses to be shared across all operations
- - support defining servers settings without subclassing `OpenAPIHandler`
- Fixes bugs: #54, #55, #68
- Renames `HttpException` class to `HTTPException` to follow [PEP 8](https://www.python.org/dev/peps/pep-0008/)

## [0.3.0] - 2020-12-16 :gear:
- Builds `wheels` and packs them in the distribution package

## [0.2.9] - 2020-12-12 🏳️
- Corrects inconsistent dependency causing an error in `pip-20.3.1`

## [0.2.8] - 2020-12-10 📜
- Links to the new website with documentation: [https://www.neoteroi.dev/blacksheep/](https://www.neoteroi.dev/blacksheep/)
- Removes links to the GitHub Wiki

## [0.2.7] - 2020-11-28 :octocat:
- Completely migrates to GitHub Workflows
- Corrects a bug in `view` method, preventing the word "name" from being a valid
  model property name
- Improves the `view` method to support built-in dataclasses, Pydantic models,
  and instances of user defined classes using `__dict__`
- Corrects bug in binding of services by name

## [0.2.6] - 2020-10-31 🎃

- Adds support for routes defined using mustaches (not only colon notation)
- Corrects two bugs happening when using `blacksheep` in Windows
- Improves the test suite to be compatible with Windows
- Adds a job running in Windows to the build and validation pipeline
- Adds `after_start` application event, fired when startup has been completed
- Adds `FromCookie` binder
- Adds automatic generation of **OpenAPI Documentation** and serving of
  Swagger UI, supporting [OpenAPI version 3](https://swagger.io/specification/) ✨
- Removes weird handling of DI `Services` and `Container` objects in the
  application
- Adds support for list of items to `BodyBinder`
- Adds `python-dateutil` dependency, and support for `datetime` and `date` to
  binders (i.e. possibility to have these automatically parsed and injected to
  request handlers' calls)
- Raises exception for a `typing.ForwardRef` during handlers normalization

## [0.2.5] - 2020-09-19 💯

- **100% test coverage**, with more than _1000_ tests
- Adds `py.types` file to the distribution package, related to
  [PEP484 stubs files](https://www.python.org/dev/peps/pep-0484/) (.pyi)
- Improves type annotations and work experience with **MyPy** and **Pylance**
- Adds support for specifying route paths when serving static files
- Adds support for serving static files from multiple folders
- Features to serve SPAs that use HTML5 History API for client side routing
- Corrects default headers feature
- Removes the rudimentary and obsolete sync logging middlewares
- Makes Jinja2 a required dependency and removes boilerplate used to make it
  optional
- Corrects default JSON dumps to handle dataclasses in `responses`

## [0.2.4] - 2020-09-08 💎

- Refactors the implementation of `binders` to be always type compliant (breaking change)
- Corrects handling of default parameters for binders
- Handles `UUID` bound parameters to request handlers
- Adds more tests for binders
- Sorts route handlers at application start
- Improves `pyi` and type annotations using recommendations from [Pylance](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance)
- Upgrades to `httptools 0.1.*` to match the version used in recent versions of `uvicorn`

## [0.2.3] - 2020-08-22 🐌

- Adds a changelog
- Adds a code of conduct
- Replaces [`aiofiles`](https://github.com/Tinche/aiofiles) with dedicated file handling
- Improves code quality
- Improves code for integration tests
- Fixes bug [#37](https://github.com/Neoteroi/BlackSheep/issues/37)
