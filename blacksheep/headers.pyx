from collections.abc import Mapping, MutableSequence
from typing import Dict, List, Tuple, Union


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

    cpdef tuple get(self, bytes name):
        cdef list results = []
        cdef tuple header
        name = name.lower()
        for header in self.values:
            if header[0].lower() == name:
                results.append(header[1])
        return tuple(results)

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

    def update(self, dict values: Dict[bytes, bytes]):
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

    def __setitem__(self, bytes key, bytes value):
        # Not obvious, but here we make the decision that setter removes existing headers with matching name:
        # it feels more natural with syntax: headers[b'X-Foo'] = b'Something'
        self.set(key, value)

    def __getitem__(self, bytes item):
        return self.get(item)

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

    def __delitem__(self, bytes key):
        self.remove(key)

    def __contains__(self, bytes key):
        return self.contains(key)

    def __repr__(self):
        return f'<Headers {self.values}>'
