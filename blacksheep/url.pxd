# cython: language_level=3
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT


cdef class URL:

    cdef readonly bytes value
    cdef readonly bytes schema
    cdef readonly bytes host
    cdef readonly int port
    cdef readonly bytes path
    cdef readonly bytes query
    cdef readonly bytes fragment
    cdef readonly bint is_absolute

    cpdef URL join(self, URL other)
    cpdef URL base_url(self)
    cpdef URL with_host(self, bytes host)
    cpdef URL with_scheme(self, bytes schema)
    cpdef URL with_query(self, bytes query)


cpdef URL build_absolute_url(
    bytes scheme,
    bytes host,
    bytes base_path,
    bytes path
)
