# cython: language_level=3
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT

from .headers cimport HttpHeaders, HttpHeader
from .contents cimport HttpContent
from .cookies cimport HttpCookie
from .messages cimport HttpRequest, HttpResponse


cpdef bytes get_status_line(int status)

cpdef bint is_small_request(HttpRequest request)

cpdef bytes write_small_request(HttpRequest request)

cdef bint is_small_response(HttpResponse response)

cdef bytes write_small_response(HttpResponse response)

