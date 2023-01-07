import os


def truthy(value: str, default: bool = False) -> bool:
    if not value:
        return default
    return value.upper() in {"1", "TRUE"}


class EnvironmentSettings:
    show_error_details: bool
    mount_auto_events: bool

    def __init__(self) -> None:
        self.show_error_details = truthy(os.environ.get("APP_SHOW_ERROR_DETAILS", ""))
        self.mount_auto_events = truthy(os.environ.get("APP_MOUNT_AUTO_EVENTS", ""))
