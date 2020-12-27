# cython: language_level=3, embedsignature=True
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT

from .url cimport URL
from .exceptions cimport BadRequestFormat
from .cookies cimport Cookie, parse_cookie, datetime_to_cookie_format, write_cookie_for_response
from .contents cimport Content, parse_www_form_urlencoded


cdef class Message:
    cdef list __headers
    cdef public Content content

    cpdef list get_headers(self, bytes key)
    cpdef bytes get_first_header(self, bytes key)
    cpdef bytes get_single_header(self, bytes key)
    cpdef void remove_header(self, bytes key)
    cdef bint _has_header(self, bytes key)
    cpdef bint has_header(self, bytes key)
    cdef void _add_header(self, bytes key, bytes value)
    cdef void _add_header_if_missing(self, bytes key, bytes value)
    cpdef void add_header(self, bytes key, bytes value)
    cpdef void set_header(self, bytes key, bytes value)
    cpdef bytes content_type(self)

    cdef void remove_headers(self, list headers)
    cdef list get_headers_tuples(self, bytes key)

    cpdef Message with_content(self, Content content)
    cpdef bint has_body(self)
    cpdef bint declares_content_type(self, bytes type)
    cpdef bint declares_json(self)
    cpdef bint declares_xml(self)


cdef class Request(Message):
    cdef public str method
    cdef public URL _url
    cdef public bytes _path
    cdef public bytes _raw_query
    cdef public object route_values
    cdef public object scope

    cdef dict __dict__

    cpdef bint expect_100_continue(self)


cdef class Response(Message):
    cdef public int status
    cdef public bint active
    cdef dict __dict__

    cpdef bint is_redirect(self)


cpdef bint method_without_body(str method)

cpdef bint is_cors_request(Request request)

cpdef bint is_cors_preflight_request(Request request)
