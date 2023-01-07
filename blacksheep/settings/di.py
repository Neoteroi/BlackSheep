from typing import Callable, Optional, Type, TypeVar, Union

from rodi import Container, ContainerProtocol, Services

T = TypeVar("T")


class RodiCI:
    def __init__(self) -> None:
        self.container = Container()
        self._provider: Optional[Services] = None

    def register(self, obj_type, *args):
        self.container.add_transient(obj_type)

    def resolve(self, obj_type: Union[Type[T], str], *args) -> T:
        if self._provider is None:
            self._provider = self.container.build_provider()
        return self._provider.get(obj_type)

    def __contains__(self, item) -> bool:
        return self.container.__contains__(item)


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
