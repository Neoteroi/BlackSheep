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
    cdef object _data
    cdef object _file
    cdef readonly bytes content_type
    cdef readonly bytes file_name
    cdef readonly bytes charset
    cdef readonly int size


cdef class FileBuffer:
    cdef public str name
    cdef public str file_name
    cdef public str content_type
    cdef public object file
    cdef public int size
    cdef public str _charset


cdef class StreamingFormPart:
    cdef readonly str name
    cdef readonly str file_name
    cdef readonly str content_type
    cdef readonly str charset
    cdef readonly object _data_stream


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
