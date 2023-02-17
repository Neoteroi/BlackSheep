from typing import List, Optional, Sequence, Union

from .utils import AnyStr, ensure_str


class InvalidRangeValue(ValueError):
    def __init__(self, message="Invalid Range"):
        super().__init__(message)


RangeValueType = Optional[int]
RangeInputValueType = Union[None, str, int]


class RangePart:
    __slots__ = ("_start", "_end")

    def __init__(self, start: RangeInputValueType, end: RangeInputValueType):
        self._start = None
        self._end = None
        self.start = start
        self.end = end

    @property
    def start(self) -> RangeValueType:
        return self._start

    @property
    def end(self) -> RangeValueType:
        return self._end

    @start.setter
    def start(self, value: RangeInputValueType):
        self._start = self._parse_value(value)
        self._validate_values()

    @end.setter
    def end(self, value: RangeInputValueType):
        self._end = self._parse_value(value)
        self._validate_values()

    def _parse_value(self, value: RangeInputValueType) -> RangeValueType:
        if value:
            return int(value)
        return None

    def _validate_value(self, value: RangeValueType):
        if value is None:
            return
        if value < 0:
            raise ValueError("A range value cannot be a negative integer.")

    def _validate_values(self):
        self._validate_value(self._start)
        self._validate_value(self._end)
        if self._start is not None and self._end is not None:
            if self._start > self._end:
                raise ValueError("The end bound must be greater than the start bound.")

    def __eq__(self, other):
        if isinstance(other, RangePart):
            return other.start == self.start and other.end == self.end
        return NotImplemented

    def can_satisfy(self, size: int) -> bool:
        """
        Returns a value indicating whether this range part can
        satisfy a given size.
        """
        if self._end is not None:
            return self._end <= size
        if self._start is not None:
            return self._start <= size
        raise TypeError("Expected either an end or a start")

    @property
    def is_suffix_length(self) -> bool:
        """
        Returns a value indicating whether this range part refers to a
        number of units at the end of the file;
        without start byte position.
        """
        return self.start is None or self.start == ""

    @property
    def is_to_end(self):
        """
        Returns a value indicating whether this range part refers to all
        bytes after a certain index; without end byte position.
        """
        return self.end is None or self.end == ""

    def __repr__(self):
        return (
            f'{self._start if self._start is not None else ""}'
            f'-{self._end if self._end is not None else ""}'
        )


def _parse_range_value(range_value: str):
    # <range-start>-  ... from start to end
    # <range-start>-<range-end>  ... portion
    # <range-start>-<range-end>, <range-start>-<range-end>, \
    #   <range-start>-<range-end>  ... portions
    # -<suffix-length>  ... last n bytes
    for portion in range_value.split(","):
        # portions are expected to contain an hyphen sign
        if "-" not in portion:
            raise InvalidRangeValue()

        try:
            # NB: value error can happen both in case of a portion containing
            # more than one hyphen (like trying to
            # define a negative number of bytes), and in the case of value
            # that cannot be converted to int
            if portion.lstrip().startswith("-"):
                yield RangePart(None, abs(int(portion)))
            else:
                start, end = portion.split("-")
                yield RangePart(start or None, end or None)
        except ValueError:
            raise InvalidRangeValue()


class Range:
    __slots__ = ("_unit", "_parts")

    def __init__(self, unit: str, parts: Sequence[RangePart]):
        self._unit: str
        self._parts: List[RangePart]
        self.unit = unit
        self.parts = parts

    def __repr__(self):
        return f'<Range {self.unit}={", ".join(map(repr, self.parts))}>'

    def __eq__(self, other):
        if isinstance(other, Range):
            return other.unit == self.unit and other.parts == self.parts
        return NotImplemented

    def __iter__(self):
        yield from self.parts

    def can_satisfy(self, size: int) -> bool:
        """
        Returns a value indicating whether this range
        can satisfy a given size.
        """
        return all(part.can_satisfy(size) for part in self.parts)

    @property
    def unit(self) -> str:
        return self._unit

    @unit.setter
    def unit(self, value: str):
        self._unit = value

    @property
    def is_multipart(self) -> bool:
        return len(self.parts) > 1

    @property
    def parts(self) -> List[RangePart]:
        return self._parts

    @parts.setter
    def parts(self, value: Sequence[RangePart]):
        self._parts = list(value)

    @classmethod
    def parse(cls, value: AnyStr):
        value = ensure_str(value)

        # an equal sign is expected in Range value;
        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Range
        if "=" not in value:
            raise InvalidRangeValue()

        try:
            unit, range_value = value.strip().split("=")
        except ValueError:
            raise InvalidRangeValue()

        return cls(unit, list(_parse_range_value(range_value)))
