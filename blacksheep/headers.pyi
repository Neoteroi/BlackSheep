from collections.abc import Mapping, MutableSequence
from typing import Union, Dict, List, Tuple, Optional, Generator


class Header:

    def __init__(self, name: bytes, value: bytes):
        self.name = name
        self.value = value

    def __repr__(self):
        return f'<Header {self.name}: {self.value}>'

    def __iter__(self) -> Generator[bytes, None, None]:
        yield self.name
        yield self.value

    def __eq__(self, other):
        if isinstance(other, Header):
            return other.name.lower() == self.name.lower() and other.value == self.value
        return NotImplemented


HeaderType = Tuple[bytes, bytes]


class Headers:

    def __init__(self, values: Optional[List[HeaderType]] = None):
        self.values = values

    def get(self, name: bytes) -> Tuple[HeaderType]: ...

    def get_tuples(self, name: bytes) -> List[HeaderType]: ...

    def get_first(self, key: bytes) -> bytes: ...

    def get_single(self, key: bytes) -> bytes: ...

    def merge(self, values: List[HeaderType]): ...

    def update(self, values: Dict[bytes, bytes]): ...

    def items(self) -> Generator[HeaderType, None, None]: ...

    def clone(self) -> Headers: ...

    def add_many(self, values: Union[Dict[bytes, bytes], List[Tuple[bytes, bytes]]]):
        if isinstance(values, MutableSequence):
            for item in values:
                self.add(*item)
            return

        if isinstance(values, Mapping):
            for key, value in values.items():
                self.add(key, value)
            return
        raise ValueError('values must be Dict[bytes, bytes] or List[Header]')

    def __add__(self, other):
        return self._add_to_instance(self.clone(), other)

    def __radd__(self, other):
        return self._add_to_instance(self.clone(), other)

    def __iadd__(self, other):
        return self._add_to_instance(self, other)

    def __iter__(self):
        yield from self.values

    def __setitem__(self, key: bytes, value: bytes): ...

    def __getitem__(self, item: bytes): ...

    def keys(self) -> Tuple[bytes]: ...

    def add(self, name: bytes, value: bytes):
        self.values.append((name, value))

    def set(self, name: bytes, value: bytes):
        if self.contains(name):
            self.remove(name)
        self.add(name, value)

    def remove(self, key: bytes): ...

    def contains(self, key: bytes) -> bool: ...

    def __delitem__(self, key: bytes):
        self.remove(key)

    def __contains__(self, key: bytes) -> bool:
        return self.contains(key)

    def __repr__(self):
        return f'<Headers {self.values}>'
