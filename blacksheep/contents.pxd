# cython: language_level=3, embedsignature=True
# Copyright (C) 2018-present Roberto Prevato
#
# This module is part of BlackSheep and is released under
# the MIT License https://opensource.org/licenses/MIT


cdef class Content:
    cdef readonly bytes type
    cdef readonly object body
    cdef readonly object generator
    cdef readonly int length
    cdef bint _is_generator_async


cdef class TextContent(Content):
    pass


cdef class HtmlContent(Content):
    pass


cdef class JsonContent(Content):
    pass


cdef class FormContent(Content):
    pass


cdef class FormPart:
    cdef readonly bytes name
    cdef readonly bytes data
    cdef readonly bytes content_type
    cdef readonly bytes file_name
    cdef readonly bytes charset


cdef class MultiPartFormData(Content):
    cdef readonly list parts
    cdef readonly bytes boundary


cpdef bytes extract_multipart_form_data_boundary(bytes content_type)


cdef dict parse_www_form_urlencoded(bytes content)


cpdef list parse_multipart_form_data(bytes content, bytes boundary)
