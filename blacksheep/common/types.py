"""
Common types annotations and functions.
"""

from typing import AnyStr, Dict, Iterable, List, Optional, Tuple, Union

from blacksheep.url import URL

KeyValuePair = Tuple[AnyStr, AnyStr]
HeadersType = Union[Dict[AnyStr, AnyStr], Iterable[KeyValuePair]]
ParamsType = Union[Dict[AnyStr, AnyStr], Iterable[KeyValuePair]]
URLType = Union[str, bytes, URL]


def _ensure_header_bytes(value: AnyStr) -> bytes:
    return value if isinstance(value, bytes) else value.encode("ascii")


def _ensure_param_str(value: AnyStr) -> str:
    return value if isinstance(value, str) else value.decode("ascii")


def normalize_headers(
    headers: Optional[HeadersType],
) -> Optional[List[Tuple[bytes, bytes]]]:
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


def normalize_params(params: Optional[ParamsType]) -> Optional[List[Tuple[str, str]]]:
    if params is None:
        return None
    if isinstance(params, dict):
        return [
            (_ensure_param_str(key), _ensure_param_str(value))  # type: ignore
            for key, value in params.items()
        ]
    return [(_ensure_param_str(key), _ensure_param_str(value)) for key, value in params]
