"""
Common types annotations and functions.
"""

from typing import AnyStr, Iterable

from blacksheep.url import URL

KeyValuePair = tuple[AnyStr, AnyStr]
HeadersType = dict[AnyStr, AnyStr] | Iterable[KeyValuePair]
ParamsType = dict[AnyStr, AnyStr] | Iterable[KeyValuePair]
URLType = str | bytes | URL


def _ensure_header_bytes(value: AnyStr) -> bytes:
    return value if isinstance(value, bytes) else value.encode("ascii")


def _ensure_param_str(value: AnyStr) -> str:
    return value if isinstance(value, str) else value.decode("ascii")


def normalize_headers(
    headers: HeadersType | None,
) -> list[tuple[bytes, bytes]] | None:
    if headers is None:
        return None
    if isinstance(headers, dict):
        return [
            (_ensure_header_bytes(key), _ensure_header_bytes(value))  # type: ignore
            for key, value in headers.items()
        ]
    return [
        (_ensure_header_bytes(key), _ensure_header_bytes(value))
        for key, value in headers
    ]


def normalize_params(params: ParamsType | None) -> list[tuple[str, str]] | None:
    if params is None:
        return None
    if isinstance(params, dict):
        return [
            (_ensure_param_str(key), _ensure_param_str(value))  # type: ignore
            for key, value in params.items()
        ]
    return [(_ensure_param_str(key), _ensure_param_str(value)) for key, value in params]
