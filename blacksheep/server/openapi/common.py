import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar, Union

from blacksheep.messages import Request
from blacksheep.server.application import Application
from blacksheep.server.files.static import get_response_for_static_content
from blacksheep.server.resources import get_resource_file_content
from blacksheep.server.responses import FriendlyEncoderExtended
from blacksheep.server.routing import Route, Router
from openapidocs.common import Format, OpenAPIRoot, Serializer

T = TypeVar("T")


@dataclass
class RequestBodyInfo:
    description: Optional[str] = None
    examples: Optional[Dict[str, Any]] = None


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
    request_body: Optional[RequestBodyInfo] = None
    responses: Optional[Dict[ResponseStatusType, Union[str, ResponseInfo]]] = None
    ignored: Optional[bool] = None
    deprecated: Optional[bool] = None
    on_created: Optional[Callable[[Any, Any], None]] = None


OpenAPIRootType = TypeVar("OpenAPIRootType", bound=OpenAPIRoot)


class OpenAPIEndpointException(Exception):
    pass


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
    ) -> None:
        self._handlers_docs: Dict[Any, EndpointDocs] = {}
        self.use_docstrings: bool = True
        self.include: Optional[Callable[[str, Route], bool]] = None
        self.ui_path = ui_path
        self.json_spec_path = json_spec_path
        self.yaml_spec_path = yaml_spec_path
        self._ui_html: bytes = b""
        self._json_docs: bytes = b""
        self._yaml_docs: bytes = b""
        self.preferred_format = preferred_format

    def __call__(
        self,
        doc: Optional[EndpointDocs] = None,
        *,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        request_body: Optional[RequestBodyInfo] = None,
        responses: Optional[Dict[ResponseStatusType, Union[str, ResponseInfo]]] = None,
        ignored: Optional[bool] = None,
        deprecated: Optional[bool] = None,
        on_created: Optional[Callable[[Any, Any], None]] = None,
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
                ignored=ignored,
                deprecated=deprecated,
                on_created=on_created,
            )
            return fn

        return decorator

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
        summary = docs.summary if docs else None

        if summary:
            return summary

        if self.use_docstrings:
            doc = handler.__doc__
            if doc:
                assert isinstance(doc, str)
                return doc.strip().splitlines()[0]
        return None

    def get_description(self, handler: Any) -> Optional[str]:
        docs = self.get_handler_docs(handler)
        description = docs.description if docs else None

        if description:
            return description

        if self.use_docstrings:
            doc = handler.__doc__
            if doc:
                return doc.strip()
        return None

    def ignore(self):
        """Excludes a request handler from API documentation."""

        def decorator(fn):
            self.get_handler_docs_or_set(fn).ignored = True
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
        if docs and docs.deprecated is not None:
            return docs.deprecated
        return None

    def router_to_paths_dict(
        self, router: Router, mapper: Callable[[Route], T]
    ) -> Dict[str, Dict[str, T]]:
        routes_dictionary: Dict[str, Dict[str, T]] = {}

        for method, routes in router.routes.items():
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

    def get_openapi_ui_html(self) -> str:
        """
        Returns the HTML response to serve the Swagger UI.
        """
        return get_resource_file_content("openapi-ui.html").replace(
            "##SPEC_URL##", self.get_spec_path()
        )

    def register_docs_ui_handler(self, app: Application) -> None:
        current_time = datetime.utcnow().timestamp()

        @self.ignore()
        @app.route(self.ui_path, methods=["GET"])
        def get_open_api_ui(request: Request):
            return get_response_for_static_content(
                request, b"text/html; charset=utf-8", self._ui_html, current_time
            )

    def register_docs_handler(self, app: Application) -> None:
        current_time = datetime.utcnow().timestamp()

        @self.ignore()
        @app.route(self.json_spec_path, methods=["GET", "HEAD"])
        def get_open_api_json(request: Request):
            return get_response_for_static_content(
                request,
                b"application/json",
                self._json_docs,
                current_time,
                cache_time=1,
            )

        @self.ignore()
        @app.route(self.yaml_spec_path, methods=["GET", "HEAD"])
        def get_open_api_yaml(request: Request):
            return get_response_for_static_content(
                request, b"text/yaml", self._yaml_docs, current_time, cache_time=1
            )

    def normalize_example(self, value: Any) -> Any:
        """
        This method is used to ensure that YAML representations of objects look
        exactly the same as JSON representations.
        """
        return json.loads(json.dumps(value, cls=FriendlyEncoderExtended))

    @abstractmethod
    def generate_documentation(self, app: Application) -> OpenAPIRootType:
        """Produces the object that describes the API."""

    def on_docs_generated(self, docs: OpenAPIRootType) -> None:
        """
        Extensibility point. Override this method to modify an OpenAPI object
        before it is serialized to JSON and YAML format.
        """

    async def build_docs(self, app: Application) -> None:
        docs = self.generate_documentation(app)
        self.on_docs_generated(docs)
        serializer = Serializer()
        self._ui_html = self.get_openapi_ui_html().encode("utf8")
        self._json_docs = serializer.to_json(docs).encode("utf8")
        self._yaml_docs = serializer.to_yaml(docs).encode("utf8")

    def bind_app(self, app: Application) -> None:
        if app.started:
            raise TypeError(
                "The application is already started. "
                "Use this method before starting the application."
            )

        self.register_docs_ui_handler(app)
        self.register_docs_handler(app)

        app.after_start += self.build_docs
