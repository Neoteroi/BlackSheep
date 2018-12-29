# cython: language_level=3, embedsignature=True
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT


cdef class Cookie:
    cdef object _expiration
    cdef public bytes name
    cdef public bytes value
    cdef public bytes expires
    cdef public bytes domain
    cdef public bytes path
    cdef public bint http_only
    cdef public bint secure
    cdef public bytes max_age
    cdef public bytes same_site
    cpdef Cookie clone(self)
    cpdef void set_max_age(self, int max_age)


cpdef Cookie parse_cookie(bytes value)


cpdef bytes datetime_to_cookie_format(object value)


cpdef object datetime_from_cookie_format(bytes value)
