"""
This module provides a strategy and classes to convert optional string representations
of values into expected types. This is used to offer a good user experience to
developers: rather than parsing raw input values from requests manually, they can
declare the expected types using Python type annotations, and the code tries to obtain
objects of the exact type.

The following code only offers default implementations that should work in most cases,
the user can still define custom logic to parse input values.
"""

from abc import ABC, abstractmethod
from datetime import date, datetime
from enum import IntEnum, StrEnum
from typing import Any, List, Literal, Optional, get_args
from urllib.parse import unquote
from uuid import UUID

from dateutil.parser import parse as dateutil_parser

from blacksheep.exceptions import BadRequest
from blacksheep.utils import ensure_str


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

    def convert(self, value: Optional[str], expected_type) -> Any:
        return unquote(value) if value else None


class InitTypeConverter(TypeConverter):

    def __init__(self, obj_type) -> None:
        self._handled_type = obj_type

    def can_convert(self, expected_type) -> bool:
        return expected_type is self._handled_type

    def convert(self, value: Optional[str], expected_type) -> Any:
        return self._handled_type(value) if value is not None else None


class BoolConverter(TypeConverter):

    def can_convert(self, expected_type) -> bool:
        return expected_type is bool

    def convert(self, value: Optional[str], expected_type) -> Any:
        if value is None:
            return None
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

    def convert(self, value: Optional[str], expected_type) -> Any:
        return value.encode(self._encoding) if value else None


class DateTimeConverter(TypeConverter):

    def can_convert(self, expected_type) -> bool:
        return expected_type is datetime

    def convert(self, value: Optional[str], expected_type) -> Any:
        return dateutil_parser(value) if value else None


class DateConverter(TypeConverter):

    def can_convert(self, expected_type) -> bool:
        return expected_type is date

    def convert(self, value: Optional[str], expected_type) -> Any:
        return dateutil_parser(value).date() if value else None


class EnumConverter(TypeConverter):

    @abstractmethod
    def parse_by_value(self, value: Optional[str], expected_type) -> Any:
        """Obtains an enum of the expected type by value."""

    @abstractmethod
    def parse_by_key(self, value: Optional[str], expected_type) -> Any:
        """Obtains an enum of the expected type by key."""

    def convert(self, value: Optional[str], expected_type) -> Any:
        if value is None:
            return None
        try:
            return self.parse_by_value(value, expected_type)
        except ValueError:
            try:
                return self.parse_by_key(value, expected_type)
            except KeyError:
                raise BadRequest(f"{value} is not a valid {expected_type.__name__}")


class StrEnumConverter(EnumConverter):

    def can_convert(self, expected_type) -> bool:
        return isinstance(expected_type, type) and issubclass(expected_type, StrEnum)

    def parse_by_value(self, value: str, expected_type) -> Any:
        return expected_type(value)

    def parse_by_key(self, value: str, expected_type) -> Any:
        return expected_type[value]


class IntEnumConverter(EnumConverter):

    def can_convert(self, expected_type) -> bool:
        return isinstance(expected_type, type) and issubclass(expected_type, IntEnum)

    def parse_by_value(self, value: str, expected_type) -> Any:
        return expected_type(int(ensure_str(value)))

    def parse_by_key(self, value: str, expected_type) -> Any:
        return expected_type[value]


class LiteralConverter(TypeConverter):

    def can_convert(self, expected_type) -> bool:
        return (
            isinstance(expected_type, type)
            and hasattr(expected_type, "__origin__")
            and expected_type.__origin__ is Literal
        )

    def convert(self, value: Optional[str], expected_type) -> Any:
        if value is None:
            return None
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


converters: List[TypeConverter] = [
    BoolConverter(),
    BytesConverter(),
    DateConverter(),
    DateTimeConverter(),
    IntConverter(),
    IntEnumConverter(),
    FloatConverter(),
    LiteralConverter(),
    StrConverter(),
    StrEnumConverter(),
    UUIDConverter(),
]
