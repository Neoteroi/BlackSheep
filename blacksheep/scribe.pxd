# cython: language_level=3
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT

from .contents cimport Content
from .cookies cimport Cookie
from .messages cimport Message, Request, Response


cpdef bytes get_status_line(int status)

cpdef bint is_small_request(Request request)

cpdef bint request_has_body(Request request)

cpdef bytes write_small_request(Request request)

cpdef bytes write_request_without_body(Request request)

cdef bint is_small_response(Response response)

cdef bytes write_small_response(Response response)

cdef void set_headers_for_content(Message message)

cdef void set_headers_for_response_content(Response message)

