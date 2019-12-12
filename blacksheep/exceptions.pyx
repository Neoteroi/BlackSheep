
cdef class InvalidOperation(Exception):

    def __init__(self, str message, object inner_exception=None):
        super().__init__(message)
        self.inner_exception = inner_exception


cdef class BadRequestFormat(Exception):

    def __init__(self, str message, object inner_exception=None):
        super().__init__(message)
        self.inner_exception = inner_exception


cdef class HttpException(Exception):

    def __init__(self, int status, str message = 'HTTP Exception'):
        super().__init__(message)
        self.status = status


cdef class BadRequest(HttpException):

    def __init__(self, message=None):
        super().__init__(400, message)


cdef class NotFound(HttpException):

    def __init__(self):
        super().__init__(404)


cdef class Unauthorized(HttpException):

    def __init__(self):
        super().__init__(401)


cdef class Forbidden(HttpException):

    def __init__(self):
        super().__init__(403)


cdef class RangeNotSatisfiable(HttpException):

    def __init__(self):
        super().__init__(416)


cdef class InternalServerError(HttpException):

    def __init__(self):
        super().__init__(500)


cdef class NotImplementedByServer(HttpException):

    def __init__(self):
        super().__init__(501)


cdef class InvalidArgument(Exception):

    def __init__(self, str message):
        super().__init__(message)


cdef class MessageAborted(Exception):
    def __init__(self):
        super().__init__('The message was aborted before the client sent its whole content.')
