from typing import Callable, TypeVar

from rodi import Container, ContainerProtocol

T = TypeVar("T")


def default_container_factory() -> ContainerProtocol:
    return Container()


class DISettings:
    def __init__(self):
        self._container_factory = default_container_factory

    def use(self, container_factory: Callable[[], ContainerProtocol]):
        self._container_factory = container_factory

    def get_default_container(self) -> ContainerProtocol:
        return self._container_factory()


di_settings = DISettings()
