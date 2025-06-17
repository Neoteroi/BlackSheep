"""
This module provides classes and functions to enable distributed tracing and logging
using OpenTelemetry.

Additional dependencies:
    pip install opentelemetry-distro
    opentelemetry-bootstrap --action=install

Features:

- An `use_open_telemetry` function that can be used to apply useful configuration.
- OTELMiddleware: Middleware for automatic tracing of HTTP requests.
- Environment-based configuration for OpenTelemetry resource attributes.
- Logging and tracing setup using user-provided exporters.
- Context manager and decorator utilities for tracing custom operations and function
  calls.

Usage:
    from blacksheep.server.otel import use_open_telemetry

    # Configure log_exporter and span_exporter as needed
    use_open_telemetry(app, log_exporter, span_exporter)
"""

import logging
import os
from contextlib import contextmanager
from functools import wraps
from typing import Awaitable, Callable, Dict, Optional

from opentelemetry import trace
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import SpanKind

from blacksheep import Application
from blacksheep.messages import Request, Response
from blacksheep.server.env import get_env

ExceptionHandler = Callable[[Request, Exception], Awaitable[Response]]


class OTELMiddleware:
    """
    Middleware configuring OpenTelemetry for all web requests.
    """

    def __init__(self, exc_handler: ExceptionHandler) -> None:
        self._exc_handler = exc_handler
        self._tracer = trace.get_tracer(__name__)

    async def __call__(self, request: Request, handler):
        path = request.url.path.decode("utf8")
        method = request.method
        with self._tracer.start_as_current_span(
            f"{method} {path}", kind=SpanKind.SERVER
        ) as span:
            try:
                response = await handler(request)
            except Exception as exc:
                # This approach is correct because it supports controlling the response
                # using exceptions. Unhandled exceptions are handled by the Span.
                response = await self._exc_handler(request, exc)

            self.set_span_attributes(span, request, response, path)
            return response

    def set_span_attributes(
        self, span: trace.Span, request: Request, response: Response, path: str
    ) -> None:
        """
        Configure the attributes on the span for a given request-response cycle.
        """
        # To reduce cardinality, update the span name to use the
        # route that matched the request
        route = request.route  # type: ignore
        span.update_name(f"{request.method} {route}")

        span.set_attribute("http.status_code", response.status)
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.path", path)
        span.set_attribute("http.url", request.url.value.decode())
        span.set_attribute("http.route", route)
        span.set_attribute("http.status_code", response.status)
        span.set_attribute("client.ip", request.original_client_ip)

        if response.status >= 400:
            span.set_status(trace.Status(trace.StatusCode.ERROR))


def _configure_logging(log_exporter: LogExporter, span_exporter: SpanExporter):
    """
    - Set up a custom LoggerProvider and attach a BatchLogRecordProcessor with the
      provided log_exporter.
    - Set the log level for the "opentelemetry" logger to WARNING to reduce noise.
    - Add a LoggingHandler to the root logger, ensuring OpenTelemetry logs are
      processed
    - Instrument logging with LoggingInstrumentor().instrument(set_logging_format=True)
      to ensure logs are formatted and correlated with traces.
    - Set up the tracer provider and attaches a BatchSpanProcessor for the given
      span_exporter.
    """
    log_provider = LoggerProvider()
    log_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)
    logging.getLogger().addHandler(
        LoggingHandler(level=logging.NOTSET, logger_provider=log_provider)
    )

    LoggingInstrumentor().instrument(set_logging_format=True)

    trace.set_tracer_provider(TracerProvider())
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(span_exporter)
    )  # type: ignore


def set_attributes(
    service_name: str,
    service_namespace: str = "default",
    env: str = "",
):
    """
    Sets the OTEL_RESOURCE_ATTRIBUTES environment variable with service metadata
    for OpenTelemetry.

    Args:
        service_name (str): The name of the service.
        service_namespace (str, optional): The namespace of the service. Defaults to
                                           "default".
        env (str, optional): The deployment environment. If not provided, it is
                            determined from the environment.

    Returns:
        None
    """
    if not env:
        env = get_env()
    os.environ["OTEL_RESOURCE_ATTRIBUTES"] = (
        f"service.name={service_name},"
        f"service.namespace={service_namespace},"
        f"deployment.environment={env}"
    )


def use_open_telemetry(
    app: Application,
    log_exporter: LogExporter,
    span_exporter: SpanExporter,
    middleware: Optional[OTELMiddleware] = None,
):
    """
    Configures OpenTelemetry tracing and logging for a BlackSheep application.

    This function sets up OpenTelemetry log and span exporters, configures resource
    attributes, and injects OTEL middleware for automatic tracing of HTTP requests.
    It also patches the router to track matched route patterns and ensures proper
    shutdown of the tracer provider on application stop.

    Args:
        app (Application): The BlackSheep application instance.
        log_exporter (LogExporter): The OpenTelemetry log exporter to use.
        span_exporter (SpanExporter): The OpenTelemetry span exporter to use.
        middleware (optional OTELMiddleware): Custom OTEL middleware instance.
            If not provided, the default OTELMiddleware is used.

    Returns:
        None
    """
    if os.getenv("OTEL_RESOURCE_ATTRIBUTES") is None:
        # set a default value
        set_attributes("blacksheep-app")

    _configure_logging(log_exporter, span_exporter)

    # Insert the middleware at the beginning of the middlewares list
    @app.on_middlewares_configuration
    def add_otel_middleware(app):
        app.middlewares.insert(
            0, middleware or OTELMiddleware(app.handle_request_handler_exception)
        )

    @app.on_start
    async def on_start(app):
        # Patch the router to keep track of the route pattern that matched the request,
        # if any.
        # https://www.neoteroi.dev/blacksheep/routing/#how-to-track-routes-that-matched-a-request
        def wrap_get_route_match(fn):
            @wraps(fn)
            def get_route_match(request):
                match = fn(request)
                request.route = match.pattern.decode() if match else "Not Found"
                return match

            return get_route_match

        app.router.get_match = wrap_get_route_match(app.router.get_match)

    @app.on_stop
    async def on_stop(app):
        # Try calling shutdown() on app stop to flush all remaining spans.
        try:
            trace.get_tracer_provider().shutdown()
        except AttributeError:
            pass


@contextmanager
def client_span_context(
    operation_name: str, attributes: Dict[str, str], *args, **kwargs
):
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(operation_name, kind=SpanKind.CLIENT) as span:
        span.set_attributes(attributes)
        for i, value in enumerate(args):
            span.set_attribute(f"@arg{i}", str(value))
        for key, value in kwargs.items():
            span.set_attribute(f"@{key}", str(value))
        try:
            yield
        except Exception as ex:
            span.record_exception(ex)
            span.set_attribute("ERROR", str(ex))
            span.set_attribute("http.status_code", 500)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise


def logcall(component="Service"):
    """
    Wraps a function to log each call using OpenTelemetry, as SpanKind.CLIENT.
    """

    def log_decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            with client_span_context(
                fn.__name__, {"component": component}, *args, **kwargs
            ):
                return await fn(*args, **kwargs)

        return wrapper

    return log_decorator
