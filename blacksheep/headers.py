from collections.abc import Mapping, MutableSequence
from typing import Dict, List, Tuple, Union


class Header:
    def __init__(self, name: bytes, value: bytes):
        self.name = name
        self.value = value

    def __repr__(self):
        return f"<Header {self.name}: {self.value}>"

    def __iter__(self):
        yield self.name
        yield self.value

    def __eq__(self, other):
        if isinstance(other, Header):
            return other.name.lower() == self.name.lower() and other.value == self.value
        return NotImplemented


class Headers:
    def __init__(self, values: List[Tuple[bytes, bytes]] = None):
        if values is None:
            values = []
        self.values = values

    def get(self, name: bytes) -> Tuple[bytes, ...]:
        results = []
        name = name.lower()
        for header in self.values:
            if header[0].lower() == name:
                results.append(header[1])
        return tuple(results)

    def get_tuples(self, name: bytes) -> List[Tuple[bytes, bytes]]:
        results = []
        name = name.lower()
        for header in self.values:
            if header[0].lower() == name:
                results.append(header)
        return results

    def get_first(self, key: bytes) -> Union[bytes, None]:
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

    def merge(self, values: List[Tuple[bytes, bytes]]):
        for header in values:
            if header is None:
                continue
            self.values.append(header)

    def update(self, values: Dict[bytes, bytes]):
        for key, value in values.items():
            self[key] = value

    def items(self):
        yield from self.values

    def clone(self):
        values = []
        for name, value in self.values:
            values.append((name, value))
        return Headers(values)

    def add_many(self, values: Union[Dict[bytes, bytes], List[Tuple[bytes, bytes]]]):
        if isinstance(values, MutableSequence):
            for item in values:
                self.add(*item)
            return
        if isinstance(values, Mapping):
            for key, value in values.items():
                self.add(key, value)
            return
        raise ValueError("values must be Dict[bytes, bytes] or List[Header]")

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

    def __add__(self, other):
        return self._add_to_instance(self.clone(), other)

    def __radd__(self, other):
        return self._add_to_instance(self.clone(), other)

    def __iadd__(self, other):
        return self._add_to_instance(self, other)

    def __iter__(self):
        yield from self.values

    def __setitem__(self, key: bytes, value: bytes):
        self.set(key, value)

    def __getitem__(self, item: bytes):
        return self.get(item)

    def keys(self) -> Tuple[bytes, ...]:
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

    def __delitem__(self, key: bytes):
        self.remove(key)

    def __contains__(self, key: bytes) -> bool:
        return self.contains(key)

    def __repr__(self):
        return f"<Headers {self.values}>"
