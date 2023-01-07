# cython: language_level=3, embedsignature=True
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT


cdef class Header:
    cdef readonly bytes name
    cdef readonly bytes value


cdef class Headers:
    cdef readonly list values

    cpdef tuple keys(self)

    cpdef Headers clone(self)

    cpdef tuple get(self, bytes name)

    cpdef list get_tuples(self, bytes name)

    cpdef void add(self, bytes name, bytes value)

    cpdef void set(self, bytes name, bytes value)

    cpdef bytes get_single(self, bytes name)

    cpdef bytes get_first(self, bytes name)

    cpdef void remove(self, bytes key)

    cpdef void merge(self, list values)

    cpdef bint contains(self, bytes key)
