# cython: language_level=3
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT

from .contents cimport Content, ServerSentEvent
from .cookies cimport Cookie
from .messages cimport Message, Request, Response


cdef int MAX_RESPONSE_CHUNK_SIZE

cdef bytes write_request_method(Request request)

cdef bytes _nocrlf(bytes value)

cdef void set_headers_for_content(Message message)

cdef void set_headers_for_response_content(Response message)

cpdef bytes write_sse(ServerSentEvent event)
