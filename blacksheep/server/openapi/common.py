"""
This module provides common classes to document APIs.

The purpose of these classes is to provide an abstraction layer on top of a specific
set of rules to document APIs. For example, it should be possible to generate both
OpenAPI Documentation v2 and v3 (currently only v3 is supported) from these types, and
potentially in the future v4, if it will be so different from v3.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from http import HTTPStatus
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Mapping,
    Optional,
    Type,
    TypeVar,
    Union,
)

from essentials.json import dumps
from openapidocs.common import Format, OpenAPIRoot, Serializer

from blacksheep.messages import Request
from blacksheep.server.application import Application, ApplicationSyncEvent
from blacksheep.server.authorization import allow_anonymous
from blacksheep.server.files.static import get_response_for_static_content
from blacksheep.server.routing import Route, Router
from blacksheep.utils.time import utcnow

from .ui import SwaggerUIProvider, UIOptions, UIProvider

T = TypeVar("T")


class ParameterSource(Enum):
    QUERY = "query"
    HEADER = "header"
    PATH = "path"
    COOKIE = "cookie"


@dataclass
class RequestBodyInfo:
    description: Optional[str] = None
    examples: Optional[Dict[str, Any]] = None


@dataclass
class ParameterExample:
    value: Any
    name: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None


@dataclass
class ParameterInfo:
    description: str
    value_type: Optional[Type] = None
    source: Optional[ParameterSource] = None
    required: Optional[bool] = None
    deprecated: Optional[bool] = None
    allow_empty_value: Optional[bool] = None
    example: Optional[Any] = None
    examples: Optional[Dict[str, ParameterExample]] = None


@dataclass
class ResponseExample:
    value: Any
    name: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None


@dataclass
class ContentInfo:
    type: Type[Any]
    examples: Optional[List[Union[ResponseExample, Any]]] = None
    content_type: str = "application/json"


@dataclass
class HeaderInfo:
    type: Type
    description: Optional[str] = None
    example: Any = None


@dataclass
class ResponseInfo:
    description: str
    headers: Optional[Dict[str, HeaderInfo]] = None
    content: Optional[List[ContentInfo]] = None


@dataclass
class SecurityInfo:
    name: str
    value: List[str]


ResponseStatusType = Union[int, str, HTTPStatus]


def response_status_to_str(value: ResponseStatusType) -> str:
    if isinstance(value, HTTPStatus):
        return str(value.value)  # type: ignore
    if isinstance(value, str):
        return value
    return str(value)


@dataclass
class EndpointDocs:
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    parameters: Optional[Mapping[str, ParameterInfo]] = None
    request_body: Optional[RequestBodyInfo] = None
    responses: Optional[Dict[ResponseStatusType, Union[str, ResponseInfo]]] = None
    ignored: Optional[bool] = None
    deprecated: Optional[bool] = None
    on_created: Optional[Callable[[Any, Any], None]] = None
    security: Optional[List[SecurityInfo]] = None


OpenAPIRootType = TypeVar("OpenAPIRootType", bound=OpenAPIRoot)


class OpenAPIEndpointException(Exception):
    pass


class OpenAPIEvent(ApplicationSyncEvent):
    pass


class OpenAPIEvents:
    on_operation_created: OpenAPIEvent
    on_docs_created: OpenAPIEvent
    on_paths_created: OpenAPIEvent

    def __init__(self, context) -> None:
        self.on_operation_created = OpenAPIEvent(context)
        self.on_docs_created = OpenAPIEvent(context)
        self.on_paths_created = OpenAPIEvent(context)


class APIDocsHandler(Generic[OpenAPIRootType], ABC):
    """
    Provides methods to handle the documentation for an API.
    """

    def __init__(
        self,
        *,
        ui_path: str = "/docs",
        json_spec_path: str = "/openapi.json",
        yaml_spec_path: str = "/openapi.yaml",
        preferred_format: Format = Format.JSON,
        anonymous_access: bool = True,
    ) -> None:
        self._handlers_docs: Dict[Any, EndpointDocs] = {}
        self.use_docstrings: bool = True
        self.include: Optional[Callable[[str, Route], bool]] = None
        self.json_spec_path = json_spec_path
        self.yaml_spec_path = yaml_spec_path
        self._json_docs: bytes = b""
        self._yaml_docs: bytes = b""
        self.preferred_format = preferred_format
        self.anonymous_access = anonymous_access
        self.ui_providers: List[UIProvider] = [SwaggerUIProvider(ui_path)]
        self._types_schemas = {}
        self.events = OpenAPIEvents(self)
        self.handle_optional_response_with_404 = True

    def __call__(
        self,
        doc: Optional[EndpointDocs] = None,
        *,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        parameters: Optional[Mapping[str, ParameterInfo]] = None,
        request_body: Optional[RequestBodyInfo] = None,
        responses: Optional[Dict[ResponseStatusType, Union[str, ResponseInfo]]] = None,
        ignored: Optional[bool] = None,
        deprecated: Optional[bool] = None,
        on_created: Optional[Callable[[Any, Any], None]] = None,
        security: Optional[List[SecurityInfo]] = None,
    ) -> Any:
        def decorator(fn):
            if doc:
                self._handlers_docs[fn] = doc
                return fn

            self._handlers_docs[fn] = EndpointDocs(
                summary=summary,
                description=description,
                tags=tags,
                request_body=request_body,
                responses=responses,
                parameters=parameters,
                ignored=ignored,
                deprecated=deprecated,
                on_created=on_created,
                security=security,
            )
            return fn

        return decorator

    def register(self, schema) -> Any:
        """
        Registers a schema for a class. When the documentation handler needs
        to obtain a schema for the decorated type, it uses the explicity schema rather
        than an auto-generated schema.
        """

        def class_decorator(cls):
            self.set_type_schema(cls, schema)
            return cls

        return class_decorator

    def set_type_schema(self, object_type, schema) -> None:
        """
        Sets a schema to be used for a class. When the documentation handler needs
        to obtain a schema for the decorated type, it uses the explicity schema rather
        than an auto-generated schema.
        """
        self._types_schemas[object_type] = schema

    def get_handler_docs(self, obj: Any) -> Optional[EndpointDocs]:
        return self._handlers_docs.get(obj)

    def get_handler_docs_or_set(self, obj: Any) -> EndpointDocs:
        if obj in self._handlers_docs:
            return self._handlers_docs[obj]
        docs = EndpointDocs()
        self._handlers_docs[obj] = docs
        return docs

    def get_summary(self, handler: Any) -> Optional[str]:
        docs = self.get_handler_docs(handler)
        return docs.summary if docs else None

    def get_description(self, handler: Any) -> Optional[str]:
        docs = self.get_handler_docs(handler)
        return docs.description if docs else None

    def ignore(self, value: bool = True):
        """Excludes a request handler from API documentation."""

        def decorator(fn):
            self.get_handler_docs_or_set(fn).ignored = value
            return fn

        return decorator

    def deprecated(self):
        def decorator(fn):
            self.get_handler_docs_or_set(fn).deprecated = True
            return fn

        return decorator

    def summary(self, text: str):
        """Assigns a summary to a request handler."""

        def decorator(fn):
            self.get_handler_docs_or_set(fn).summary = text
            return fn

        return decorator

    def tags(self, *tags: str):
        """Assigns tags to a request handler."""

        def decorator(fn):
            self.get_handler_docs_or_set(fn).tags = list(tags)
            return fn

        return decorator

    def _get_request_handler(self, route: Route) -> Any:
        if hasattr(route.handler, "root_fn"):
            return route.handler.root_fn
        # this happens rarely, when an app doesn't apply any middleware and
        # any normalization
        return route.handler  # pragma: no cover

    def get_handler_tags(self, handler: Any) -> Optional[List[str]]:
        docs = self.get_handler_docs(handler)
        if docs and docs.tags:
            return docs.tags

        if hasattr(handler, "controller_type"):
            # default to controller's class name for the tags
            return [handler.controller_type.class_name().title()]

        return None

    def is_deprecated(self, handler: Any) -> Optional[bool]:
        docs = self.get_handler_docs(handler)
        return docs.deprecated if docs else None

    def router_to_paths_dict(
        self, router: Router, mapper: Callable[[Route], T]
    ) -> Dict[str, Dict[str, T]]:
        routes_dictionary: Dict[str, Dict[str, T]] = {}

        for method, routes in router.routes.items():
            if b"_" in method:
                # Non standard method, used internally to support more scenarios.
                # This is used for WebSocket.
                continue

            for route in routes:
                key = route.mustache_pattern

                if self.include and not self.include(key, route):
                    continue

                handler = self._get_request_handler(route)
                docs = self.get_handler_docs(handler)

                if docs and docs.ignored:
                    continue

                if key not in routes_dictionary:
                    if "*" in key:
                        # ignore catch-all routes from api docs
                        continue
                    routes_dictionary[key] = {}
                routes_dictionary[key][method.decode("utf8").lower()] = mapper(route)

        return routes_dictionary

    def get_spec_path(self) -> str:
        if self.preferred_format == Format.JSON:
            return self.json_spec_path

        if self.preferred_format == Format.YAML:
            return self.yaml_spec_path

        raise OpenAPIEndpointException(
            f"Unhandled preferred format {self.preferred_format}"
        )

    def register_docs_handler(self, app: Application) -> None:
        current_time = utcnow().timestamp()

        @self.ignore()
        @allow_anonymous(self.anonymous_access)
        @app.router.route(self.json_spec_path, methods=["GET", "HEAD"])
        def get_open_api_json(request: Request):
            return get_response_for_static_content(
                request,
                b"application/json",
                self._json_docs,
                current_time,
                cache_time=1,
            )

        @self.ignore()
        @allow_anonymous(self.anonymous_access)
        @app.router.route(self.yaml_spec_path, methods=["GET", "HEAD"])
        def get_open_api_yaml(request: Request):
            return get_response_for_static_content(
                request, b"text/yaml", self._yaml_docs, current_time, cache_time=1
            )

    def normalize_example(self, value: Any) -> Any:
        """
        This method is used to ensure that YAML representations of objects look
        exactly the same as JSON representations.
        """
        return json.loads(dumps(value))

    @abstractmethod
    def generate_documentation(self, app: Application) -> OpenAPIRootType:
        """Produces the object that describes the API."""

    def on_docs_generated(self, docs: OpenAPIRootType) -> None:
        """
        Extensibility point. Override this method to modify an OpenAPI object
        before it is serialized to JSON and YAML format.
        """

    def get_ui_page_title(self) -> str:
        return "API Docs"  # pragma: no cover

    async def build_docs(self, app: Application) -> None:
        docs = self.generate_documentation(app)
        self.on_docs_generated(docs)
        serializer = Serializer()

        ui_options = UIOptions(
            spec_url=self.get_spec_path(), page_title=self.get_ui_page_title()
        )

        for ui_provider in self.ui_providers:
            ui_provider.build_ui(ui_options)

        self._json_docs = serializer.to_json(docs).encode("utf8")
        self._yaml_docs = serializer.to_yaml(docs).encode("utf8")

    def bind_app(self, app: Application) -> None:
        if app.started:
            raise TypeError(
                "The application is already started. "
                "Use this method before starting the application."
            )

        for ui_provider in self.ui_providers:
            ui_handler = ui_provider.get_ui_handler()
            ui_handler = self.ignore()(ui_handler)
            ui_handler = allow_anonymous(self.anonymous_access)(ui_handler)
            app.router.add_get(ui_provider.ui_path, ui_handler)

        self.register_docs_handler(app)

        app.after_start += self.build_docs
