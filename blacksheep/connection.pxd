# cython: language_level=3, embedsignature=True
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT

from .headers cimport HttpHeader
from .messages cimport HttpRequest, HttpResponse


cdef class ConnectionHandler:
    cdef readonly object app
    cdef readonly HttpRequest request
    cdef int max_body_size
    cdef public object transport
    cdef readonly float time_of_last_activity
    cdef object loop
    cdef bint reading_paused
    cdef bint writing_paused
    cdef object writable
    cdef bint closed

    cdef object parser
    cdef object url
    cdef bytes method
    cdef list headers
