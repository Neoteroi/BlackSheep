# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.3] - 2020-08-22 🐌

- Adds a changelog
- Adds a code of conduct
- Replaces [`aiofiles`](https://github.com/Tinche/aiofiles) with dedicated file handling
- Improves code quality
- Improves code for integration tests
- Fixes bug [#37](https://github.com/RobertoPrevato/BlackSheep/issues/37)

## [0.2.4] - 2020-09-08 💎

- Refactors the implementation of `binders` to be always type compliant (breaking change)
- Corrects handling of default parameters for binders
- Handles `UUID` bound parameters to request handlers
- Adds more tests for binders
- Sorts route handlers at application start
- Improves `pyi` and type annotations using recommendations from [Pylance](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance)
- Upgrades to `httptools 0.1.*` to match the version used in recent versions of `uvicorn`
