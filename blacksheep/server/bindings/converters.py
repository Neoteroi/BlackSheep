"""
This module provides a strategy and classes to convert client input into expected types.
This is used to offer a good user experience to developers: rather than parsing raw
input values from requests manually, they can declare the expected types using Python
type annotations, and the code tries to obtain objects of the expected type.

The following code only offers default implementations that should work in most cases,
the user can still define custom logic to parse input values.
"""

import inspect
from abc import ABC, abstractmethod
from collections.abc import Sequence as SequenceABC
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import (
    Any,
    Callable,
    List,
    Literal,
    Sequence,
    get_args,
    get_origin,
    get_type_hints,
)
from urllib.parse import unquote
from uuid import UUID

from blacksheep.exceptions import BadRequest
from blacksheep.server.bindings.dates import parse_datetime
from blacksheep.utils import ensure_str

try:
    # Supported only in Python >= 3.11
    from enum import IntEnum, StrEnum
except ImportError:
    IntEnum = None
    StrEnum = None

try:
    # Pydantic v2 support
    from pydantic import BaseModel
except ImportError:
    BaseModel = None


class TypeConverter(ABC):
    """
    Base class for types that converts string reprensentations of values into
    instances of specific types.
    """

    @abstractmethod
    def can_convert(self, expected_type) -> bool:
        """Returns True if this converter can handle the expected type."""

    @abstractmethod
    def convert(self, value, expected_type) -> Any:
        """Converts a str value into an object of the expected type."""


class StrConverter(TypeConverter):

    def can_convert(self, expected_type) -> bool:
        return expected_type is str or str(expected_type) == "~T"

    def convert(self, value, expected_type) -> Any:
        if value is None:
            return None
        if "%" in value:
            return unquote(value)
        return value


class InitTypeConverter(TypeConverter):

    def __init__(self, obj_type) -> None:
        self._handled_type = obj_type

    def can_convert(self, expected_type) -> bool:
        return expected_type is self._handled_type

    def convert(self, value, expected_type) -> Any:
        return self._handled_type(value) if value is not None else None


class BoolConverter(TypeConverter):

    def can_convert(self, expected_type) -> bool:
        return expected_type is bool

    def convert(self, value, expected_type) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return bool(value)
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

    def convert(self, value, expected_type) -> Any:
        return value.encode(self._encoding) if value else None


class DateTimeConverter(TypeConverter):

    def __init__(self, parser_fn: Callable[[str], datetime] = parse_datetime) -> None:
        self.parser_fn = parser_fn

    def can_convert(self, expected_type) -> bool:
        return expected_type is datetime

    def convert(self, value, expected_type) -> Any:
        return self.parser_fn(value) if value else None


class DateConverter(TypeConverter):

    def __init__(self, parser_fn: Callable[[str], datetime] = parse_datetime) -> None:
        self.parser_fn = parser_fn

    def can_convert(self, expected_type) -> bool:
        return expected_type is date

    def convert(self, value, expected_type) -> Any:
        return self.parser_fn(value).date() if value else None


class EnumConverter(TypeConverter):

    @abstractmethod
    def parse_by_value(self, value, expected_type) -> Any:
        """Obtains an enum of the expected type by value."""

    @abstractmethod
    def parse_by_key(self, value, expected_type) -> Any:
        """Obtains an enum of the expected type by key."""

    def convert(self, value, expected_type) -> Any:
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

    def __init__(self, case_insensitive: bool = False) -> None:
        self.case_insensitive = case_insensitive

    def can_convert(self, expected_type) -> bool:
        return (
            hasattr(expected_type, "__origin__") and expected_type.__origin__ is Literal
        )

    def convert(self, value, expected_type) -> Any:
        if value is None:
            return None
        allowed = get_args(expected_type)
        for allowed_value in allowed:
            if str(allowed_value) == value:
                return allowed_value
            if (
                self.case_insensitive
                and isinstance(allowed_value, str)
                and allowed_value.lower() == value.lower()
            ):
                return allowed_value
        raise ValueError(f"{value!r} is not a valid {expected_type}")


class _AsIsConverter(TypeConverter):
    def can_convert(self, expected_type) -> bool:
        return True

    def convert(self, value, expected_type) -> Any:
        return value


_as_is_converter = _AsIsConverter()


class DictConverter(TypeConverter):
    """
    Converter for dict[K, V] where both K and V can be handled by converters.
    Supports string keys and hashable class keys.
    """

    def can_convert(self, expected_type) -> bool:
        return _get_origin(expected_type) is dict

    def convert(self, value, expected_type) -> Any:
        if value is None:
            return None

        key_type, value_type = _get_args(expected_type)

        # Find the appropriate converters
        key_converter = get_converter(key_type)
        value_converter = get_converter(value_type)

        return {
            key_converter.convert(k, key_type): value_converter.convert(v, value_type)
            for k, v in value.items()
        }


_dict_converter = DictConverter()


@lru_cache(maxsize=None)
def _get_signature(cls):
    return inspect.signature(cls.__init__)


@lru_cache(maxsize=None)
def _get_type_hints(cls):
    return get_type_hints(cls.__init__)


@lru_cache(maxsize=None)
def _get_dataclass_fields(cls):
    return fields(cls)


@lru_cache(maxsize=None)
def _is_pydantic_model(cls):
    return BaseModel is not None and inspect.isclass(cls) and issubclass(cls, BaseModel)


@lru_cache(maxsize=None)
def _get_args(cls):
    return get_args(cls)


@lru_cache(maxsize=None)
def _get_origin(cls):
    return get_origin(cls)


@lru_cache(maxsize=None)
def _is_dataclass(cls):
    return is_dataclass(cls)


class ClassConverter(TypeConverter):
    """
    Converts dictionaries to instances of desired types, supporting Pydantic models,
    Python dataclasses or plain user-defined classes.

    This converter handles common scenarios for basic type conversion from dictionaries
    to class instances. It supports:
    - Dataclasses with simple field types
    - Plain classes with __init__ parameters
    - Nested classes and dataclasses

    Important limitations:
    - This converter is NOT designed to support all possible type conversion scenarios
    - It handles only straightforward cases with basic type annotations
    - Complex type validation, nested generics, and advanced typing constructs
      are not fully supported

    For complex type conversion scenarios, use:
    - Pydantic models (recommended): Provides comprehensive validation,
      advanced typing support, and better error messages
    - Custom type converters: Define explicit conversion logic for your specific needs
    - Explicit conversion in your input types classes

    This converter ignores extra fields in the input dictionary that don't match
    class parameters or dataclass fields.
    """

    def _from_dict(self, cls, data: dict | list):
        """Convert dict to plain class or dataclass, ignoring extra fields"""

        if _is_pydantic_model(cls):
            return cls.model_validate(data)

        # here it is sufficient to handle list because input from client can only
        # be parsed as list in most cases (like after parsing JSON or XML), not other
        # types of sequences like tuple
        if isinstance(data, list):
            # require a type hint to work
            obj_type_hint = _get_args(cls)
            if obj_type_hint:
                # good…
                obj_type_converter = get_converter(obj_type_hint[0])
                return [
                    obj_type_converter.convert(datum, obj_type_hint[0])
                    for datum in data
                ]
            else:
                # return data as-is (let if fail downstream if it must)
                return data

        if _dict_converter.can_convert(cls):
            return _dict_converter.convert(data, cls)

        if not isinstance(data, dict):
            return data

        # Handle dataclasses
        if _is_dataclass(cls):
            return self._handle_dataclass(cls, data)

        # Handle plain classes
        return self._handle_plain_class(cls, data)

    def _handle_dataclass(self, cls, data):
        field_values = {}
        for field in _get_dataclass_fields(cls):
            if field.name in data:
                field_type = field.type
                value = data[field.name]
                if value is None:
                    field_values[field.name] = None
                else:
                    converter = get_converter(field_type)
                    field_values[field.name] = converter.convert(value, field_type)
        return cls(**field_values)

    def _handle_plain_class(self, cls, data):
        # Get type hints from __init__
        sig = _get_signature(cls)
        type_hints = _get_type_hints(cls)

        init_params = {}
        for param_name, _ in sig.parameters.items():
            if param_name == "self":
                continue

            if param_name in data:
                value = data[param_name]

                # Check if parameter has a type hint that's a class
                if param_name in type_hints:
                    param_type = type_hints[param_name]
                    converter = get_converter(param_type)
                    init_params[param_name] = converter.convert(value, param_type)
                else:
                    init_params[param_name] = value
        return cls(**init_params)

    @lru_cache(maxsize=None)
    def can_convert(self, expected_type) -> bool:
        # Must be a class
        if not inspect.isclass(expected_type):
            return False

        if is_dataclass(expected_type) or _is_pydantic_model(expected_type):
            return True

        # Exclude built-in types
        if expected_type.__module__ == "builtins":
            return False

        # Exclude typing module generics
        if get_origin(expected_type) is not None:
            return False

        # Must have a callable __init__ method
        if not hasattr(expected_type, "__init__"):
            return False

        return True

    def convert(self, value, expected_type) -> Any:
        if value is None:
            return None

        return self._from_dict(expected_type, value)


class ListConverter(TypeConverter):
    """
    Converter for list[T], Sequence[T], and tuple[T] where T
    is handled by class_converters (DataClass, Pydantic models, plain classes).
    """

    def __init__(self, supported_origins=None):
        if supported_origins is None:
            supported_origins = {list, List, Sequence, SequenceABC, tuple}
        self.supported_origins = frozenset(supported_origins)

    def can_convert(self, expected_type) -> bool:
        origin = _get_origin(expected_type)
        if origin not in self.supported_origins:
            return False

        # Get the item type
        args = _get_args(expected_type)
        if not args:
            return False

        return True

    def convert(self, value, expected_type) -> Any:
        if value is None:
            return None

        origin = _get_origin(expected_type)
        item_type = _get_args(expected_type)[0]

        item_converter = get_converter(item_type)

        converted_items = [item_converter.convert(item, item_type) for item in value]

        if origin in {list, List}:
            return converted_items
        elif origin is tuple:
            return tuple(converted_items)
        else:
            return converted_items


converters: list[TypeConverter] = [
    BoolConverter(),
    BytesConverter(),
    DateConverter(),
    DateTimeConverter(),
    IntConverter(),
    FloatConverter(),
    LiteralConverter(),
    StrConverter(),
    UUIDConverter(),
]


if StrEnum is not None and IntEnum is not None:
    # Python > 3.10
    converters.append(IntEnumConverter())
    converters.append(StrEnumConverter())


class_converters: list[TypeConverter] = [
    ClassConverter(),
    ListConverter(),
    DictConverter(),
]


@lru_cache(maxsize=None)
def get_converter(cls) -> TypeConverter:
    _all_converters = converters + class_converters

    for converter in _all_converters:
        if converter.can_convert(cls):
            return converter
    return _as_is_converter
