from rodi import Container
from blacksheep.settings.di import di_settings

from typing import Any

# Singleton instance of the container for the application services.
# The container will be used as default service container in Application.
services = di_settings.get_default_container()


def scoped(target: Any):
    """Decorator to register a scoped service in the DI container."""
    if not isinstance(services, Container):
        raise RuntimeError("Cannot register a scoped service in a non rodi container.")
    services.add_scoped(target)
    return target


def transient(target: Any):
    """Decorator to register a transient service in the DI container."""
    if not isinstance(services, Container):
        raise RuntimeError(
            "Cannot register a transient service in a non rodi container."
        )
    services.add_transient(target)
    return target


def singleton(target: Any):
    """Decorator to register a singleton service in the DI container."""
    if not isinstance(services, Container):
        raise RuntimeError(
            "Cannot register a singleton service in a non rodi container."
        )
    services.add_singleton(target)
    return target


def alias(alias: str):
    """Decorator to register an alias for a service in the DI container."""

    def deco(target: Any) -> Any:
        if not isinstance(services, Container):
            raise RuntimeError("Cannot register an alias in a non rodi container.")
        services.add_alias(alias, target)
        return target

    return deco
