# cython: language_level=3, embedsignature=True
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT

from .exceptions cimport HttpException


cdef class BaseApplication:

    cdef public bint show_error_details
    cdef readonly object router
    cdef readonly list connections
    cdef public dict exceptions_handlers
    cdef object get_http_exception_handler(self, HttpException http_exception)
    cdef object get_exception_handler(self, Exception exception)
