# cython: language_level=3


cdef class MessageAborted(Exception):
    pass


cdef class HTTPException(Exception):
    cdef public int status


cdef class BadRequest(HTTPException):
    pass


cdef class BadRequestFormat(BadRequest):
    cdef public object inner_exception


cdef class NotFound(HTTPException):
    pass


cdef class InvalidArgument(Exception):
    pass


cdef class InvalidOperation(Exception):
    pass
