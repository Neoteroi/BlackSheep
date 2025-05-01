# cython: language_level=3, embedsignature=True
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT


cdef class Content:
    cdef readonly bytes type
    cdef readonly bytes body
    cdef readonly long long length


cdef class StreamedContent(Content):
    cdef readonly object generator


cdef class ASGIContent(Content):
    cdef readonly object receive
    cpdef void dispose(self)


cdef class TextContent(Content):
    pass


cdef class HTMLContent(Content):
    pass


cdef class JSONContent(Content):
    pass


cdef class FormContent(Content):
    pass


cdef class FormPart:
    cdef readonly bytes name
    cdef readonly bytes data
    cdef readonly bytes content_type
    cdef readonly bytes file_name
    cdef readonly bytes charset


cdef class ServerSentEvent:
    cdef readonly object data
    cdef readonly str event
    cdef readonly str id
    cdef readonly int retry
    cdef readonly str comment
    cpdef str write_data(self)


cdef class TextServerSentEvent(ServerSentEvent):
    pass


cdef class MultiPartFormData(Content):
    cdef readonly list parts
    cdef readonly bytes boundary


cdef dict parse_www_form_urlencoded(str content)


cdef dict multiparts_to_dictionary(list parts)
