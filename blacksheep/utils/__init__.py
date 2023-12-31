import re
from typing import AnyStr, Type, TypeVar

T = TypeVar("T")


def ensure_bytes(value: AnyStr) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf8")
    raise ValueError("Expected bytes or str")


def ensure_str(value: AnyStr) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode()
    raise ValueError("Expected bytes or str")


def remove_duplicate_slashes(value: str) -> str:
    return re.sub("/{2,}", "/", value)


def join_fragments(*args: AnyStr) -> str:
    """Joins URL fragments"""
    return "/" + "/".join(
        remove_duplicate_slashes(ensure_str(arg)).strip("/") for arg in args if arg
    )


def get_class_hierarchy(cls: Type[T]):
    return cls.__mro__


def get_class_instance_hierarchy(instance: T):
    return get_class_hierarchy(type(instance))


def truthy(value: str, default: bool = False) -> bool:
    if not value:
        return default
    return value.upper() in {"1", "TRUE"}
