import os
from dataclasses import dataclass

from blacksheep.utils import truthy


def get_env() -> str:
    return os.environ.get("APP_ENV", "production")


def is_development() -> bool:
    """
    Returns a value indicating whether the application is running for local development.
    This method checks if an `APP_ENV` environment variable is set and its lowercase
    value is either "local", "dev", or "development".
    """
    return get_env().lower() in {"local", "dev", "development"}


def is_production() -> bool:
    """
    Returns a value indicating whether the application is running for the production
    environment (default is true).
    This method checks if an `APP_ENV` environment variable is set and its lowercase
    value is either "prod" or "production".
    """
    return get_env().lower() in {"prod", "production"}


def get_global_route_prefix() -> str:
    """
    Returns the global route prefix, if any, defined by the `APP_ROUTE_PREFIX`
    environment variable.
    """
    return os.environ.get("APP_ROUTE_PREFIX", "")


@dataclass(init=False, frozen=True)
class EnvironmentSettings:
    env: str
    show_error_details: bool
    mount_auto_events: bool
    use_default_router: bool
    add_signal_handler: bool
    http_scheme: str | None
    force_https: bool

    def __init__(self) -> None:
        object.__setattr__(self, "env", get_env())
        object.__setattr__(
            self,
            "show_error_details",
            truthy(os.environ.get("APP_SHOW_ERROR_DETAILS", "")),
        )
        object.__setattr__(
            self,
            "mount_auto_events",
            truthy(os.environ.get("APP_MOUNT_AUTO_EVENTS", "1")),
        )
        object.__setattr__(
            self,
            "use_default_router",
            truthy(os.environ.get("APP_DEFAULT_ROUTER", "1")),
        )
        object.__setattr__(
            self, "add_signal_handler", truthy(os.environ.get("APP_SIGNAL_HANDLER", ""))
        )
        object.__setattr__(
            self, "force_https", truthy(os.environ.get("APP_FORCE_HTTPS", ""))
        )

        http_scheme = os.environ.get("APP_HTTP_SCHEME")
        if http_scheme is not None and http_scheme not in {"http", "https"}:
            raise ValueError(
                f"Invalid APP_HTTP_SCHEME: '{http_scheme}'. Must be 'http' or 'https'."
            )
        object.__setattr__(self, "http_scheme", http_scheme)
