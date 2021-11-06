# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.1] - 2021-??-?? :shield:
- Adds built-in support to `JWT` bearer authentication, and validation
  of `JWTs` issued by identity providers implementing **OpenID Connect (OIDC)**
  discovery `/.well-known/openid-configuration` (more in general, for JWTs
  signed using asymmetric encryption and verified using public RSA keys)
- Adds built-in support for **OpenID Connect (OIDC)** **Authorization Code Grant**
  and **Hybrid** flows, which can be used to integrate with `OAuth` applications
- Adds built-in handling of `X-Forwarded` and `Forwarded` headers with
  validation, and also to handle trusted hosts
- Adds an extensibility point that enables sorting of middlewares before they
  are applied on the application
- Fixes #199
- Downgrades `httptools` dependency to version `>=0.2,<0.4`
- Adds some improvements to the testing `get_example_scope` method

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
