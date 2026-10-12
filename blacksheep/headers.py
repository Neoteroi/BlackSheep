from collections.abc import Iterable, Mapping, MutableSequence
from typing import Generator, TypeVar

_HeaderName = TypeVar("_HeaderName", bound=str | bytes)


def _encode_header_name(name: str | bytes) -> bytes:
    if isinstance(name, str):
        return name.encode("ascii")
    if not isinstance(name, bytes):
        raise TypeError("Header names must be str or bytes")
    return name


def _encode_header_value(value: str | bytes) -> bytes:
    if isinstance(value, str):
        return value.encode("latin-1")
    if not isinstance(value, bytes):
        raise TypeError("Header values must be str or bytes")
    return value


class Header:
    def __init__(self, name: bytes, value: bytes):
        self.name = name
        self.value = value

    def __repr__(self) -> str:
        return f"<Header {self.name!r}: {self.value!r}>"

    def __iter__(self) -> Generator[bytes, None, None]:
        yield self.name
        yield self.value

    def __eq__(self, other):
        if isinstance(other, Header):
            return other.name.lower() == self.name.lower() and other.value == self.value
        return NotImplemented


class Headers:
    def __init__(self, values: list[tuple[bytes, bytes]] | None = None):
        if values is None:
            values = []
        self.values = values

    @classmethod
    def from_values(
        cls,
        values: (
            Mapping[_HeaderName, str | bytes]
            | Iterable[tuple[str | bytes, str | bytes]]
        ),
    ) -> "Headers":
        """Create byte-backed headers from a mapping or iterable, preserving duplicates."""
        items = values.items() if isinstance(values, Mapping) else values
        return cls(
            [
                (_encode_header_name(name), _encode_header_value(value))
                for name, value in items
            ]
        )

    def add_text(self, name: str | bytes, value: str | bytes) -> None:
        """Append an entry without replacing matches, encoding strings at the boundary."""
        self.add(_encode_header_name(name), _encode_header_value(value))

    def get(self, name: bytes) -> tuple[bytes, ...]:
        results = []
        name = name.lower()
        for header in self.values:
            if header[0].lower() == name:
                results.append(header[1])
        return tuple(results)

    def get_text_values(
        self, name: str | bytes, encoding: str = "latin-1"
    ) -> tuple[str, ...]:
        """Decode matching values on demand, preserving separate header entries."""
        return tuple(
            value.decode(encoding) for value in self.get(_encode_header_name(name))
        )

    def get_first_text(
        self, name: str | bytes, encoding: str = "latin-1"
    ) -> str | None:
        """Decode the first matching value, or return None when absent."""
        value = self.get_first(_encode_header_name(name))
        return value.decode(encoding) if value is not None else None

    def get_single_text(self, name: str | bytes, encoding: str = "latin-1") -> str:
        """Decode exactly one matching value; raise ValueError otherwise."""
        return self.get_single(_encode_header_name(name)).decode(encoding)

    def get_tuples(self, name: bytes) -> list[tuple[bytes, bytes]]:
        results = []
        name = name.lower()
        for header in self.values:
            if header[0].lower() == name:
                results.append(header)
        return results

    def get_first(self, key: bytes) -> bytes | None:
        key = key.lower()
        for header in self.values:
            if header[0].lower() == key:
                return header[1]
        return None

    def get_single(self, key: bytes) -> bytes:
        results = self.get(key)
        if len(results) > 1:
            raise ValueError("Headers contains more than one header with the given key")
        if len(results) < 1:
            raise ValueError("Headers does not contain one header with the given key")
        return results[0]

    def merge(self, values: list[tuple[bytes, bytes]]):
        for header in values:
            if header is None:
                continue
            self.values.append(header)

    def update(self, values: Mapping[_HeaderName, bytes | str]):
        for key, value in values.items():
            self[key] = value

    def items(self) -> Generator[tuple[bytes, bytes], None, None]:
        yield from self.values

    def clone(self) -> "Headers":
        values: list[tuple[bytes, bytes]] = []
        for name, value in self.values:
            values.append((name, value))
        return Headers(values)

    def add_many(
        self, values: dict[bytes, bytes] | list[tuple[bytes, bytes]] | list[Header]
    ):
        if isinstance(values, MutableSequence):
            for item in values:
                self.add(*item)
            return
        if isinstance(values, Mapping):
            for key, value in values.items():
                self.add(key, value)
            return
        raise ValueError("values must be dict[bytes, bytes] or list[Header]")

    @staticmethod
    def _add_to_instance(
        instance,
        other: "Headers | Header | tuple[bytes, bytes] | MutableSequence[tuple[bytes, bytes]]",
    ):
        if isinstance(other, Headers):
            for value in other:
                instance.add(*value)
            return instance
        if isinstance(other, Header):
            instance.add(other.name, other.value)
            return instance
        if isinstance(other, tuple):
            if len(other) != 2:
                raise ValueError(f"Cannot add, an invalid tuple {str(other)}.")
            instance.add(*other)
            return instance
        if isinstance(other, MutableSequence):
            for value in other:
                if isinstance(value, tuple) and len(value) == 2:
                    instance.add(*value)
                else:
                    raise ValueError(
                        "The sequence contains invalid elements: cannot add "
                        f"{str(value)} to {instance.__class__.__name__}"
                    )
            return instance
        return NotImplemented

    def __add__(
        self,
        other: "Headers | Header | tuple[bytes, bytes] | MutableSequence[tuple[bytes, bytes]]",
    ):
        return self._add_to_instance(self.clone(), other)

    def __radd__(
        self,
        other: "Headers | Header | tuple[bytes, bytes] | MutableSequence[tuple[bytes, bytes]]",
    ):
        return self._add_to_instance(self.clone(), other)

    def __iadd__(
        self,
        other: "Headers | Header | tuple[bytes, bytes] | MutableSequence[tuple[bytes, bytes]]",
    ):
        return self._add_to_instance(self, other)

    def __iter__(self) -> Generator[tuple[bytes, bytes], None, None]:
        yield from self.values

    def __setitem__(self, key: str | bytes, value: str | bytes):
        """Replace matching entries, encoding text names as ASCII and values as Latin-1."""
        self.set(_encode_header_name(key), _encode_header_value(value))

    def __getitem__(self, item: str | bytes) -> tuple[bytes, ...]:
        return self.get(_encode_header_name(item))

    def keys(self) -> tuple[bytes, ...]:
        results = []
        for name, value in self.values:
            if name not in results:
                results.append(name)
        return tuple(results)

    def add(self, name: bytes, value: bytes):
        self.values.append((name, value))

    def set(self, name: bytes, value: bytes):
        if self.contains(name):
            self.remove(name)
        self.add(name, value)

    def remove(self, key: bytes):
        to_remove = []
        key = key.lower()
        for item in self.values:
            if item[0].lower() == key:
                to_remove.append(item)
        for item in to_remove:
            self.values.remove(item)

    def contains(self, key: bytes) -> bool:
        key = key.lower()
        for name, value in self.values:
            if name.lower() == key:
                return True
        return False

    def __delitem__(self, key: str | bytes):
        self.remove(_encode_header_name(key))

    def __contains__(self, key: str | bytes) -> bool:
        return self.contains(_encode_header_name(key))

    def __repr__(self) -> str:
        return f"<Headers {self.values!r}>"
