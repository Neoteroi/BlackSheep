# cython: language_level=3


cdef class MessageAborted(Exception):
    pass


cdef class BadRequestFormat(Exception):
    cdef public object inner_exception


cdef class HttpException(Exception):
    cdef public int status


cdef class BadRequest(HttpException):
    pass


cdef class NotFound(HttpException):
    pass


cdef class InvalidArgument(Exception):
    pass


cdef class InvalidOperation(Exception):
    pass
