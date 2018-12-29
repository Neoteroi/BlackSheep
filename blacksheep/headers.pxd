# cython: language_level=3, embedsignature=True
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT


cdef class Header:
    cdef readonly bytes name
    cdef readonly bytes value


cdef class Headers:
    cdef object _headers

    cpdef list get(self, bytes name)

    cpdef Header get_single(self, bytes name)

    cpdef Header get_first(self, bytes name)

    cpdef void merge(self, list values)
