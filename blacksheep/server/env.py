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


@dataclass(init=False)
class EnvironmentSettings:
    env: str
    show_error_details: bool
    mount_auto_events: bool
    use_default_router: bool

    def __init__(self) -> None:
        self.env = get_env()
        self.show_error_details = truthy(os.environ.get("APP_SHOW_ERROR_DETAILS", ""))
        self.mount_auto_events = truthy(os.environ.get("APP_MOUNT_AUTO_EVENTS", ""))
        self.use_default_router = truthy(os.environ.get("APP_DEFAULT_ROUTER", "1"))
