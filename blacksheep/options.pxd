# cython: language_level=3, embedsignature=True
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT


cdef class ServerLimits:

    cdef readonly int max_body_size
    cdef readonly int keep_alive_timeout


cdef class ServerOptions:

    cdef readonly str host
    cdef readonly int port
    cdef readonly bint no_delay
    cdef readonly int processes_count
    cdef readonly ServerLimits limits
    cdef readonly bint show_error_details
    cdef readonly int backlog
    cdef readonly object ssl_context
