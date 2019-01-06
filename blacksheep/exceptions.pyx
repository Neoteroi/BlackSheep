
cdef class InvalidOperation(Exception):

    def __init__(self, str message, object inner_exception=None):
        super().__init__(message)
        self.inner_exception = inner_exception


cdef class BadRequestFormat(Exception):

    def __init__(self, str message, object inner_exception=None):
        super().__init__(message)
        self.inner_exception = inner_exception


cdef class HttpException(Exception):

    def __init__(self, int status, str message = None):
        super().__init__(message)
        self.status = status


cdef class BadRequest(HttpException):

    def __init__(self, message=None):
        super().__init__(400, message)


cdef class NotFound(HttpException):

    def __init__(self):
        super().__init__(404)


cdef class InvalidArgument(Exception):

    def __init__(self, str message):
        super().__init__(message)


cdef class MessageAborted(Exception):
    def __init__(self):
        super().__init__('The message was aborted before the client sent its whole content.')
