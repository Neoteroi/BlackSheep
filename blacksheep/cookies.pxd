# cython: language_level=3, embedsignature=True
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT

from cpython.datetime cimport datetime


cpdef enum CookieSameSiteMode:
    UNDEFINED = 0
    LAX = 1
    STRICT = 2
    NONE = 3


cdef class Cookie:
    cdef str _name
    cdef str _value
    cdef public datetime expires
    cdef public str domain
    cdef public str path
    cdef public bint http_only
    cdef public bint secure
    cdef public int max_age
    cdef public CookieSameSiteMode same_site
    cpdef Cookie clone(self)


cpdef Cookie parse_cookie(bytes value)


cpdef bytes datetime_to_cookie_format(datetime value)


cpdef datetime datetime_from_cookie_format(bytes value)


cdef bytes write_cookie_for_response(Cookie cookie)


cdef tuple split_value(bytes raw_value, bytes separator)


cdef CookieSameSiteMode same_site_mode_from_bytes(bytes raw_value)
