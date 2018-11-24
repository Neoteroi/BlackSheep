from collections import defaultdict
from collections.abc import Mapping, MutableSequence
from typing import Union, Dict, List


cdef class HttpHeader:

    def __init__(self, bytes name, bytes value):
        self.name = name
        self.value = value

    def __repr__(self):
        return f'<HttpHeader {self.name}: {self.value}>'

    def __eq__(self, other):
        if isinstance(other, HttpHeader):
            return other.name.lower() == self.name.lower() and other.value == self.value
        return NotImplemented


cdef class HttpHeaderCollection:

    def __init__(self, list values=None):
        self._headers = defaultdict(list)
        if values:
            self.merge(values)

    cpdef void merge(self, list values):
        cdef HttpHeader header
        for header in values:
            self[header.name].append(header)

    cpdef list get(self, bytes name):
        cdef bytes key
        cdef list values
        for key, values in self._headers.items():
            if key.lower() == name.lower():
                return values
        return self._headers[name]

    def set(self, bytes name, value: Union[bytes, HttpHeader]):
        return self.__setitem__(name, value)

    def update(self, dict values):
        for key, value in values.items():
            self[key] = value

    def add(self, header: HttpHeader):
        self[header.name].append(header)

    def add_many(self, values: Union[Dict[bytes, bytes], List[HttpHeader]]):
        if isinstance(values, MutableSequence):
            for item in values:
                self[item.name].append(item)
            return

        if isinstance(values, Mapping):
            for key, value in values.items():
                self[key].append(self._get_value(key, value))
            return
        raise ValueError('values must be Dict[bytes, bytes] or List[HttpHeader]')

    def remove(self, value: Union[bytes, HttpHeader]):
        if isinstance(value, bytes):
            self._headers[value].clear()
            return True

        if isinstance(value, HttpHeader):
            for key, values in self._headers.items():
                for header in values:
                    if id(header) == id(value):
                        values.remove(value)
                        return True
        else:
            raise ValueError('value must be of bytes or HttpHeader type')
        return False

    def _get_value(self, key: bytes, value: Union[bytes, HttpHeader]):
        if isinstance(value, bytes):
            return HttpHeader(key, value)
        if isinstance(value, HttpHeader):
            return value
        raise ValueError('value must be of bytes or HttpHeader type')

    def items(self):
        for key, value in self._headers.items():
            if value:
                yield key, value

    def clone(self):
        clone = HttpHeaderCollection()
        for header in self._headers.values():
            for value in header:
                clone.add(value)
        return clone

    @staticmethod
    def _add_to_instance(instance, other):
        if isinstance(other, HttpHeaderCollection):
            for value in other:
                instance.add(value)
            return instance

        if isinstance(other, MutableSequence):
            for value in other:
                if isinstance(value, HttpHeader):
                    instance.add(value)
                else:
                    raise ValueError(f'The sequence contains invalid elements: '
                                     f'cannot add {str(value)} to {instance.__class__.__name__}')
            return instance

        if isinstance(other, HttpHeader):
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

    def __setitem__(self, bytes key, value: Union[bytes, HttpHeader]):
        # Not obvious, but here we make the decision that setter removes existing headers with matching name:
        # it feels more natural with syntax: headers[b'X-Foo'] = b'Something'
        self._headers[key] = [self._get_value(key, value)]

    def __getitem__(self, bytes item):
        return self.get(item)

    def __delitem__(self, bytes key):
        del self._headers[key]

    def __contains__(self, bytes item):
        return item in self._headers

    cpdef HttpHeader get_first(self, bytes name):
        values = self.get(name)
        return values[0] if values else None

    cpdef HttpHeader get_single(self, bytes name):
        values = self.get(name)
        if len(values) > 1:
            return values[-1]
        return values[0] if values else None

    @classmethod
    def from_param(cls, param: Union[None, 'HttpHeaderCollection', List[HttpHeader], Dict[bytes, bytes]]):
        if param is None:
            return cls()
        return cls(param)
