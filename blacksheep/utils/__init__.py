import re
from typing import AnyStr


def ensure_bytes(value: AnyStr) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode()
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
    """Joins URL fragments bytes"""
    return "/" + "/".join(
        remove_duplicate_slashes(ensure_str(arg)).strip("/") for arg in args if arg
    )
