# cython: language_level=3, embedsignature=True
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT

from .url cimport URL
from .exceptions cimport BadRequestFormat
from .headers cimport Headers, Header
from .cookies cimport Cookie, parse_cookie, datetime_to_cookie_format
from .contents cimport Content, extract_multipart_form_data_boundary, parse_www_form_urlencoded, parse_multipart_form_data


cdef class Message:
    cdef public Headers headers
    cdef readonly Content content
    cdef dict _cookies
    cdef bytearray _raw_body
    cdef public object complete
    cdef object _form_data
    cdef readonly bint aborted

    cdef void on_body(self, bytes chunk)
    cpdef void extend_body(self, bytes chunk)
    cpdef void set_content(self, Content content)
    cpdef bint has_body(self)
    cpdef bint declares_content_type(self, bytes type)
    cpdef bint declares_json(self)
    cpdef bint declares_xml(self)


cdef class Request(Message):
    cdef public bint active
    cdef public dict route_values
    cdef public URL url
    cdef public bytes method
    cdef public object services
    cdef dict _query
    cdef dict __dict__

    cpdef bint expect_100_continue(self)


cdef class Response(Message):
    cdef public int status
    cdef public bint active
    cdef dict __dict__

    cpdef bint is_redirect(self)
