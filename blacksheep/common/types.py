"""
Common types annotations and functions.
"""

from collections.abc import Mapping
from typing import AnyStr, Iterable, TypeVar

from blacksheep.headers import Headers
from blacksheep.url import URL

KeyValuePair = tuple[AnyStr, AnyStr]
_HeaderName = TypeVar("_HeaderName", bound=str | bytes)
HeadersType = (
    Mapping[_HeaderName, str | bytes] | Iterable[tuple[str | bytes, str | bytes]]
)
ParamsType = dict[AnyStr, AnyStr] | Iterable[KeyValuePair]
URLType = str | bytes | URL


def _ensure_param_str(value: AnyStr) -> str:
    return value if isinstance(value, str) else value.decode("ascii")


def normalize_headers(
    headers: HeadersType | None,
) -> list[tuple[bytes, bytes]] | None:
    if headers is None:
        return None
    return Headers.from_values(headers).values


def normalize_params(params: ParamsType | None) -> list[tuple[str, str]] | None:
    if params is None:
        return None
    if isinstance(params, dict):
        return [
            (_ensure_param_str(key), _ensure_param_str(value))  # type: ignore
            for key, value in params.items()
        ]
    return [(_ensure_param_str(key), _ensure_param_str(value)) for key, value in params]
