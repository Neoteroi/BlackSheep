"""
This module provides integration for OpenTelemetry using OTLP (OpenTelemetry Protocol)
exporters for logging and tracing in BlackSheep applications. This code is vendor
agnostic as it can work with all providers supporting the OpenTelemetry Protocol
(e.g. Grafana).

It defines a helper function to configure OpenTelemetry with OTLPLogExporter and
OTLPSpanExporter, ensuring that all required OTLP-related environment variables are set
before initialization.

Additional dependencies:
    pip install opentelemetry-exporter-otlp

Usage:
    from blacksheep.server.otel.otlp import use_open_telemetry_otlp

    use_open_telemetry_otlp(app)
"""

import os
from typing import Optional

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from blacksheep import Application

from . import OTELMiddleware, use_open_telemetry

__all__ = ["use_open_telemetry_otlp"]


def use_open_telemetry_otlp(
    app: Application, middleware: Optional[OTELMiddleware] = None
):
    """
    Configures OpenTelemetry for a BlackSheep application using OTLP exporters.

    This function checks for required OTLP-related environment variables and sets up
    OpenTelemetry logging and tracing using OTLPLogExporter and OTLPSpanExporter.

    Args:
        app: The BlackSheep Application instance.
        middleware (optional OTELMiddleware): Custom OTEL middleware instance.
            If not provided, the default OTELMiddleware is used.

    Raises:
        ValueError: If any required OTLP environment variables are missing.
    """
    expected_vars = [
        "OTEL_RESOURCE_ATTRIBUTES",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
    ]
    missing_vars = [var for var in expected_vars if os.environ.get(var) is None]
    if missing_vars:
        raise ValueError(f"Missing env variables: {', '.join(missing_vars)}")

    # The following exporters use environment variables for configuration:
    use_open_telemetry(app, OTLPLogExporter(), OTLPSpanExporter(), middleware)
