# cython: language_level=3, embedsignature=True
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT

from .headers cimport Header
from .messages cimport Request, Response
from .baseapp cimport BaseApplication


cdef class ServerConnection:
    cdef readonly BaseApplication app
    cdef readonly Request request
    cdef int max_body_size
    cdef public object transport
    cdef readonly float time_of_last_activity
    cdef object loop
    cdef bint reading_paused
    cdef bint writing_paused
    cdef object writable
    cdef bint closed
    cdef bint ignore_more_body

    cdef object parser
    cdef object url
    cdef bytes method
    cdef list headers

    cpdef void connection_made(self, transport)
    cpdef void data_received(self, bytes data)
    cpdef void connection_lost(self, exc)
    cpdef void pause_writing(self)
    cpdef void resume_writing(self)
    cpdef void on_body(self, bytes value)
    cpdef void on_headers_complete(self)
    cpdef void on_url(self, bytes url)
    cpdef void on_header(self, bytes name, bytes value)
    cpdef str get_client_ip(self)
    cpdef void reset(self)
    cpdef void eof_received(self)

    cpdef void close(self)
    cdef void dispose(self)
