import os

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


class EnvironmentSettings:
    _env: str
    _show_error_details: bool
    _mount_auto_events: bool
    _use_default_router: bool
    _add_signal_handler: bool
    _http_scheme: str | None
    _force_https: bool

    def __init__(
        self,
        env: str = "local",
        show_error_details: bool = False,
        mount_auto_events: bool = True,
        use_default_router: bool = True,
        add_signal_handler: bool = False,
        http_scheme: str | None = None,
        force_https: bool = False,
    ) -> None:
        if http_scheme is not None and http_scheme not in {"http", "https"}:
            raise ValueError(
                f"Invalid http_scheme: '{http_scheme}'. Must be 'http' or 'https'."
            )

        self._env = env
        self._show_error_details = show_error_details
        self._mount_auto_events = mount_auto_events
        self._use_default_router = use_default_router
        self._add_signal_handler = add_signal_handler
        self._http_scheme = http_scheme
        self._force_https = force_https

    @classmethod
    def from_env(cls) -> "EnvironmentSettings":
        """
        Creates an EnvironmentSettings instance by reading from environment variables.
        """
        return cls(
            env=get_env(),
            show_error_details=truthy(os.environ.get("APP_SHOW_ERROR_DETAILS", "")),
            mount_auto_events=truthy(os.environ.get("APP_MOUNT_AUTO_EVENTS", "1")),
            use_default_router=truthy(os.environ.get("APP_DEFAULT_ROUTER", "1")),
            add_signal_handler=truthy(os.environ.get("APP_SIGNAL_HANDLER", "")),
            http_scheme=os.environ.get("APP_HTTP_SCHEME"),
            force_https=truthy(os.environ.get("APP_FORCE_HTTPS", "")),
        )

    @property
    def env(self) -> str:
        return self._env

    @property
    def show_error_details(self) -> bool:
        return self._show_error_details

    @property
    def mount_auto_events(self) -> bool:
        return self._mount_auto_events

    @property
    def use_default_router(self) -> bool:
        return self._use_default_router

    @property
    def add_signal_handler(self) -> bool:
        return self._add_signal_handler

    @property
    def http_scheme(self) -> str | None:
        return self._http_scheme

    @property
    def force_https(self) -> bool:
        return self._force_https
