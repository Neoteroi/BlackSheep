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
        return unquote(value) if value else None


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

    @staticmethod
    def _is_pydantic_model(expected_type):
        return (
            BaseModel is not None
            and inspect.isclass(expected_type)
            and issubclass(expected_type, BaseModel)
        )

    def _from_dict(self, cls, data: dict | list):
        """Convert dict to plain class or dataclass, ignoring extra fields"""

        if self._is_pydantic_model(cls):
            return cls.model_validate(data)

        # here it is sufficient to handle list because input from client can only
        # be parsed as list in most cases (like after parsing JSON or XML), not other
        # types of sequences like tuple
        if isinstance(data, list):
            # require a type hint to work
            obj_type_hint = get_args(cls)
            if obj_type_hint:
                # good…
                for converter in class_converters:
                    if converter.can_convert(obj_type_hint[0]):
                        return [
                            converter.convert(datum, obj_type_hint[0]) for datum in data
                        ]
                return [datum for datum in data]
            else:
                # return data as-is (let if fail if it must)
                return data

        if not isinstance(data, dict):
            return data

        # Handle dataclasses
        if hasattr(cls, "__dataclass_fields__"):
            field_values = {}
            for field in fields(cls):
                if field.name in data:
                    field_type = field.type
                    value = data[field.name]
                    # Handle nested classes
                    if hasattr(field_type, "__init__"):
                        field_values[field.name] = self._from_dict(field_type, value)
                    else:
                        field_values[field.name] = value
            return cls(**field_values)

        # Handle plain classes
        # Get type hints from __init__
        sig = inspect.signature(cls.__init__)
        type_hints = get_type_hints(cls.__init__)

        init_params = {}
        for param_name, _ in sig.parameters.items():
            if param_name == "self":
                continue

            if param_name in data:
                value = data[param_name]

                # Check if parameter has a type hint that's a class
                if param_name in type_hints:
                    param_type = type_hints[param_name]
                    if hasattr(param_type, "__init__") and not isinstance(
                        param_type, type(None)
                    ):
                        init_params[param_name] = self._from_dict(param_type, value)
                    else:
                        init_params[param_name] = value
                else:
                    init_params[param_name] = value
        return cls(**init_params)

    def can_convert(self, expected_type) -> bool:
        # Must be a class
        if not inspect.isclass(expected_type):
            return False

        if is_dataclass(expected_type) or self._is_pydantic_model(expected_type):
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


# Add this new converter class after the existing converters
class ListConverter(TypeConverter):
    """
    Converter for list[T], Sequence[T], and tuple[T] where T
    is handled by class_converters (DataClass, Pydantic models, plain classes).
    """

    def __init__(self, supported_origins=None):
        if supported_origins is None:
            supported_origins = {list, List, Sequence, SequenceABC, tuple}
        self.supported_origins = supported_origins

    def can_convert(self, expected_type) -> bool:
        origin = get_origin(expected_type)
        if origin not in self.supported_origins:
            return False

        # Get the item type
        args = get_args(expected_type)
        if not args:
            return False

        item_type = args[0]

        # Check if any class converter can handle the item type
        for converter in class_converters:
            if converter.can_convert(item_type):
                return True

        return False

    def convert(self, value, expected_type) -> Any:
        if value is None:
            return None

        if not isinstance(value, list):
            raise ValueError(f"Expected a list for {expected_type}, got {type(value)}")

        origin = get_origin(expected_type)
        item_type = get_args(expected_type)[0]

        # Find the appropriate converter for the item type
        item_converter = None
        for converter in class_converters:
            if converter.can_convert(item_type):
                item_converter = converter
                break

        if item_converter is None:
            raise ValueError(f"No converter found for item type {item_type}")

        # Convert each item in the list
        converted_items = []
        for item in value:
            converted_item = item_converter.convert(item, item_type)
            converted_items.append(converted_item)

        # Return the appropriate collection type
        if origin in {list, List}:
            return converted_items
        elif origin in {tuple}:
            return tuple(converted_items)
        else:
            # For Sequence and other abstract types, default to list
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
]
