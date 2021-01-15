# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.2] - 2021-01-xx
- Logs handled and unhandled exceptions (fixes: #75)

## [0.3.1] - 2020-12-27 🎄
- Implements an abstraction layer to [handle CORS](https://www.neoteroi.dev/blacksheep/cors/)
- Improves the code API to handle [response cookies](https://www.neoteroi.dev/blacksheep/responses/#setting-cookies)
- Improves the default handling of authorization for request handlers (#69)
- Adds more binders: `FromText`, `FromBytes`, `RequestMethod`, `RequestURL`
- Improves `FromJson` binder to support returning the dictionary after JSON deserialization
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
- Fixes bug [#37](https://github.com/RobertoPrevato/BlackSheep/issues/37)
