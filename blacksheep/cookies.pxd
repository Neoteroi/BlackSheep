# cython: language_level=3, embedsignature=True
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT


cdef class HttpCookie:
    cdef object _expiration
    cdef readonly bytes name
    cdef readonly bytes value
    cdef readonly bytes expires
    cdef readonly bytes domain
    cdef readonly bytes path
    cdef readonly bint http_only
    cdef readonly bint secure
    cdef readonly bytes max_age
    cdef readonly bytes same_site


cpdef HttpCookie parse_cookie(bytes value)


cpdef bytes datetime_to_cookie_format(object value)


cpdef object datetime_from_cookie_format(bytes value)
