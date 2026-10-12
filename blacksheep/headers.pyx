from collections.abc import Iterable, Mapping, MutableSequence
from typing import TypeVar

_HeaderName = TypeVar("_HeaderName", bound=str | bytes)

cdef inline bytes _encode_header_name(object name):
    cdef bytes raw_name = name.encode("ascii") if isinstance(name, str) else name
    if raw_name is None:
        raise TypeError("Header names must be str or bytes")
    return raw_name


cdef inline bytes _encode_header_value(object value):
    cdef bytes raw_value = value.encode("latin-1") if isinstance(value, str) else value
    if raw_value is None:
        raise TypeError("Header values must be str or bytes")
    return raw_value


cdef class Header:

    def __init__(self, bytes name, bytes value):
        self.name = name
        self.value = value

    def __repr__(self):
        return f'<Header {self.name}: {self.value}>'

    def __iter__(self):
        yield self.name
        yield self.value

    def __eq__(self, other):
        if isinstance(other, Header):
            return other.name.lower() == self.name.lower() and other.value == self.value
        return NotImplemented


cdef class Headers:

    def __init__(self, list values = None):
        if values is None:
            values = []
        self.values = values

    @classmethod
    def from_values(
        cls,
        values: Mapping[_HeaderName, str | bytes]
        | Iterable[tuple[str | bytes, str | bytes]],
    ):
        """Create byte-backed headers from a mapping or iterable, preserving duplicates."""
        items = values.items() if isinstance(values, Mapping) else values
        return cls([
            (_encode_header_name(name), _encode_header_value(value))
            for name, value in items
        ])

    def add_text(self, name: str | bytes, value: str | bytes):
        """Append an entry without replacing matches, encoding strings at the boundary."""
        self.add(_encode_header_name(name), _encode_header_value(value))

    cpdef tuple get(self, bytes name):
        cdef list results = []
        cdef tuple header
        name = name.lower()
        for header in self.values:
            if header[0].lower() == name:
                results.append(header[1])
        return tuple(results)

    def get_text_values(self, name: str | bytes, str encoding = "latin-1"):
        """Decode matching values on demand, preserving separate header entries."""
        cdef bytes raw_name = _encode_header_name(name)
        return tuple(value.decode(encoding) for value in self.get(raw_name))

    def get_first_text(self, name: str | bytes, str encoding = "latin-1"):
        """Decode the first matching value, or return None when absent."""
        cdef bytes value = self.get_first(_encode_header_name(name))
        return value.decode(encoding) if value is not None else None

    def get_single_text(self, name: str | bytes, str encoding = "latin-1"):
        """Decode exactly one matching value; raise ValueError otherwise."""
        return self.get_single(_encode_header_name(name)).decode(encoding)

    cpdef list get_tuples(self, bytes name):
        cdef list results = []
        cdef tuple header
        name = name.lower()
        for header in self.values:
            if header[0].lower() == name:
                results.append(header)
        return results

    cpdef bytes get_first(self, bytes key):
        cdef tuple header
        key = key.lower()
        for header in self.values:
            if header[0].lower() == key:
                return header[1]

    cpdef bytes get_single(self, bytes key):
        cdef tuple results = self.get(key)
        if len(results) > 1:
            raise ValueError('Headers contains more than one header with the given key')
        if len(results) < 1:
            raise ValueError('Headers does not contain one header with the given key')
        return results[0]

    cpdef void merge(self, list values):
        cdef tuple header
        for header in values:
            if header is None:
                continue
            self.values.append(header)

    def update(self, values: Mapping[_HeaderName, bytes | str]):
        for key, value in values.items():
            self[key] = value

    def items(self):
        yield from self.values

    cpdef Headers clone(self):
        cdef list values = []
        cdef bytes name, value
        for name, value in self.values:
            values.append((name, value))
        return Headers(values)

    def add_many(self, values):
        if isinstance(values, MutableSequence):
            for item in values:
                self.add(*item)
            return

        if isinstance(values, Mapping):
            for key, value in values.items():
                self.add(key, value)
            return
        raise ValueError('values must be dict[bytes, bytes] or list[Header]')

    @staticmethod
    def _add_to_instance(instance, other):
        if isinstance(other, Headers):
            for value in other:
                instance.add(*value)
            return instance

        if isinstance(other, Header):
            instance.add(other.name, other.value)
            return instance

        if isinstance(other, tuple):
            if len(other) != 2:
                raise ValueError(f'Cannot add, an invalid tuple {str(other)}.')
            instance.add(*other)
            return instance

        if isinstance(other, MutableSequence):
            for value in other:
                if isinstance(value, tuple) and len(value) == 2:
                    instance.add(*value)
                else:
                    raise ValueError(f'The sequence contains invalid elements: '
                                     f'cannot add {str(value)} to {instance.__class__.__name__}')
            return instance

        return NotImplemented

    def __add__(self, other):
        return self._add_to_instance(self.clone(), other)

    def __radd__(self, other):
        return self._add_to_instance(self.clone(), other)

    def __iadd__(self, other):
        return self._add_to_instance(self, other)

    def __iter__(self):
        yield from self.values

    def __setitem__(self, key: str | bytes, value: str | bytes):
        """Replace matching entries, encoding text names as ASCII and values as Latin-1."""
        # Not obvious, but here we make the decision that setter removes existing headers with matching name:
        # it feels more natural with syntax: headers[b'X-Foo'] = b'Something'
        self.set(_encode_header_name(key), _encode_header_value(value))

    def __getitem__(self, item: str | bytes):
        return self.get(_encode_header_name(item))

    cpdef tuple keys(self):
        cdef bytes name, value
        cdef list results = []

        for name, value in self.values:
            if name not in results:
                results.append(name)
        return tuple(results)

    cpdef void add(self, bytes name, bytes value):
        self.values.append((name, value))

    cpdef void set(self, bytes name, bytes value):
        if self.contains(name):
            self.remove(name)
        self.add(name, value)

    cpdef void remove(self, bytes key):
        cdef tuple item
        cdef list to_remove = []
        key = key.lower()

        for item in self.values:
            if item[0].lower() == key:
                to_remove.append(item)

        for item in to_remove:
            self.values.remove(item)

    cpdef bint contains(self, bytes key):
        cdef bytes name, value
        key = key.lower()

        for name, value in self.values:
            if name.lower() == key:
                return True
        return False

    def __delitem__(self, key: str | bytes):
        self.remove(_encode_header_name(key))

    def __contains__(self, key: str | bytes):
        return self.contains(_encode_header_name(key))

    def __repr__(self):
        return f'<Headers {self.values}>'
