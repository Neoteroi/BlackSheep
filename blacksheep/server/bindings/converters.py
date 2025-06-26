from abc import ABC, abstractmethod
from base64 import urlsafe_b64decode
from collections.abc import Iterable
from datetime import date, datetime
from enum import IntEnum, StrEnum
from typing import Any, List, Literal, Sequence, get_args
from urllib.parse import unquote
from uuid import UUID

from dateutil.parser import parse as dateutil_parser


class TypeConverter(ABC):
    """
    Base class for types that converts string reprensentations of values into
    instances of specific types.
    """

    @abstractmethod
    def can_convert(self, expected_type) -> bool:
        """Returns True if this converter can handle the expected type."""

    @abstractmethod
    def convert(self, value: Any, expected_type) -> Any:
        """Converts a str value into an object of the expected type."""


class StrConverter(TypeConverter):

    def can_convert(self, expected_type) -> bool:
        return expected_type is str or str(expected_type) == "~T"

    def convert(self, value: str, expected_type) -> Any:
        return unquote(value) if value else None


class InitTypeConverter(TypeConverter):

    def __init__(self, obj_type) -> None:
        self._handled_type = obj_type

    def can_convert(self, expected_type) -> bool:
        return expected_type is self._handled_type

    def convert(self, value: str, expected_type) -> Any:
        return self._handled_type(value)


class BoolConverter(TypeConverter):

    def can_convert(self, expected_type) -> bool:
        return expected_type is bool

    def convert(self, value: str, expected_type) -> Any:
        if value.lower() in ("true", "1"):
            return True
        elif value.lower() in ("false", "0"):
            return False
        else:
            raise ValueError(f"Cannot convert {value!r} to {expected_type.__name__}")


class IntConverter(InitTypeConverter):

    def __init__(self) -> None:
        super().__init__(int)


class FloatConverter(InitTypeConverter):

    def __init__(self) -> None:
        super().__init__(float)


class UUIDConverter(InitTypeConverter):

    def __init__(self) -> None:
        super().__init__(UUID)


class BytesConverter(TypeConverter):

    def __init__(self, encoding: str = "utf8") -> None:
        self._encoding = encoding

    def can_convert(self, expected_type) -> bool:
        return expected_type is bytes

    def convert(self, value: str, expected_type) -> Any:
        return (
            urlsafe_b64decode(value.encode(self._encoding)).decode(self._encoding)
            if value
            else None
        )


class DateTimeConverter(TypeConverter):

    def can_convert(self, expected_type) -> bool:
        return expected_type is datetime

    def convert(self, value: str, expected_type) -> Any:
        return dateutil_parser(value) if value else None


class DateConverter(TypeConverter):

    def can_convert(self, expected_type) -> bool:
        return expected_type is date

    def convert(self, value: str, expected_type) -> Any:
        return dateutil_parser(value).date() if value else None


class EnumConverter(TypeConverter):

    def can_convert(self, expected_type) -> bool:
        return isinstance(expected_type, type) and issubclass(
            expected_type, (IntEnum, StrEnum)
        )

    def convert(self, value: str, expected_type) -> Any:
        try:
            return expected_type(value)
        except ValueError:
            try:
                return expected_type[value]
            except KeyError:
                raise ValueError(f"{value} is not a valid {expected_type.__name__}")


class IterableConverter(TypeConverter):

    def _is_generic_iterable_annotation(self, param_type):
        return hasattr(param_type, "__origin__") and (
            param_type.__origin__ in {list, tuple, set}
            or issubclass(param_type.__origin__, Iterable)
        )

    def can_convert(self, expected_type) -> bool:
        return self._is_generic_iterable_annotation(expected_type) or expected_type in {
            list,
            set,
            tuple,
        }

    def convert(self, value: Sequence[str], expected_type) -> Any:
        return super().convert(value, expected_type)


class LiteralConverter(TypeConverter):

    def can_convert(self, expected_type) -> bool:
        return (
            isinstance(expected_type, type)
            and hasattr(expected_type, "__origin__")
            and expected_type.__origin__ is Literal
        )

    def convert(self, value: str, expected_type) -> Any:
        allowed = get_args(expected_type)
        for allowed_value in allowed:
            if (
                isinstance(allowed_value, str)
                and allowed_value.lower() == value.lower()
            ):
                return allowed_value
            if allowed_value == value:
                return allowed_value
        raise ValueError(f"{value!r} is not a valid {expected_type}")


Converters: List[TypeConverter] = [
    BytesConverter(),
    BoolConverter(),
    DateConverter(),
    DateTimeConverter(),
    EnumConverter(),
    IntConverter(),
    FloatConverter(),
    LiteralConverter(),
    StrConverter(),
    UUIDConverter(),
]
