from collections import defaultdict
from collections.abc import Mapping, MutableSequence
from typing import Union, Dict, List


cdef class Header:

    def __init__(self, bytes name, bytes value):
        self.name = name
        self.value = value

    def __repr__(self):
        return f'<Header {self.name}: {self.value}>'

    def __eq__(self, other):
        if isinstance(other, Header):
            return other.name.lower() == self.name.lower() and other.value == self.value
        return NotImplemented


cdef class Headers:

    def __init__(self, list values=None):
        self._headers = defaultdict(list)
        if values:
            self.merge(values)

    cpdef void merge(self, list values):
        cdef Header header
        for header in values:
            self[header.name].append(header)

    cpdef list get(self, bytes name):
        cdef bytes key
        cdef list values
        for key, values in self._headers.items():
            if key.lower() == name.lower():
                return values
        return self._headers[name]

    def set(self, bytes name, value: Union[bytes, Header]):
        return self.__setitem__(name, value)

    def update(self, dict values):
        for key, value in values.items():
            self[key] = value

    def add(self, header: Header):
        self[header.name].append(header)

    def add_many(self, values: Union[Dict[bytes, bytes], List[Header]]):
        if isinstance(values, MutableSequence):
            for item in values:
                self[item.name].append(item)
            return

        if isinstance(values, Mapping):
            for key, value in values.items():
                self[key].append(self._get_value(key, value))
            return
        raise ValueError('values must be Dict[bytes, bytes] or List[Header]')

    def remove(self, value: Union[bytes, Header]):
        if isinstance(value, bytes):
            self._headers[value].clear()
            return True

        if isinstance(value, Header):
            for key, values in self._headers.items():
                for header in values:
                    if id(header) == id(value):
                        values.remove(value)
                        return True
        else:
            raise ValueError('value must be of bytes or Header type')
        return False

    def _get_value(self, key: bytes, value: Union[bytes, Header]):
        if isinstance(value, bytes):
            return Header(key, value)
        if isinstance(value, Header):
            return value
        raise ValueError('value must be of bytes or Header type')

    def items(self):
        cdef bytes key
        cdef list value

        for key, value in self._headers.items():
            if value:
                yield key, value

    def clone(self):
        clone = Headers()
        for header in self._headers.values():
            for value in header:
                clone.add(value)
        return clone

    @staticmethod
    def _add_to_instance(instance, other):
        if isinstance(other, Headers):
            for value in other:
                instance.add(value)
            return instance

        if isinstance(other, MutableSequence):
            for value in other:
                if isinstance(value, Header):
                    instance.add(value)
                else:
                    raise ValueError(f'The sequence contains invalid elements: '
                                     f'cannot add {str(value)} to {instance.__class__.__name__}')
            return instance

        if isinstance(other, Header):
            instance.add(other)
            return instance

        return NotImplemented

    def __add__(self, other):
        return self._add_to_instance(self.clone(), other)

    def __radd__(self, other):
        return self._add_to_instance(self.clone(), other)

    def __iadd__(self, other):
        return self._add_to_instance(self, other)

    def __iter__(self):
        for key, value in self._headers.items():
            for header in value:
                yield header

    def __setitem__(self, bytes key, value: Union[bytes, Header]):
        # Not obvious, but here we make the decision that setter removes existing headers with matching name:
        # it feels more natural with syntax: headers[b'X-Foo'] = b'Something'
        self._headers[key] = [self._get_value(key, value)]

    def __getitem__(self, bytes item):
        return self.get(item)

    def __delitem__(self, bytes key):
        del self._headers[key]

    def __contains__(self, bytes key):
        cdef bytes existing_key
        cdef bytes lower_key = key.lower()

        for existing_key in self._headers.keys():
            if existing_key.lower() == lower_key:
                return True
        return False

    cpdef Header get_first(self, bytes name):
        values = self.get(name)
        return values[0] if values else None

    cpdef Header get_single(self, bytes name):
        values = self.get(name)
        if len(values) > 1:
            return values[-1]
        return values[0] if values else None

    def __repr__(self):
        try:
            return f'<Headers at {id(self)} ({b", ".join(self._headers.keys())).decode()})>'
        except Exception:
            return f'<Headers at {id(self)} ({len(self._headers)})>'
