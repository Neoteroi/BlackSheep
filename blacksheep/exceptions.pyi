
class InvalidOperation(Exception):

    def __init__(self, message: str, inner_exception: object=None):
        super().__init__(message)
        self.inner_exception = inner_exception


class BadRequestFormat(Exception):

    def __init__(self, message: str, inner_exception: object=None):
        super().__init__(message)
        self.inner_exception = inner_exception


class HttpException(Exception):

    def __init__(self, status: int, message: str = 'HTTP Exception'):
        super().__init__(message)
        self.status = status


class BadRequest(HttpException):

    def __init__(self, message: str):
        super().__init__(400, message)


class NotFound(HttpException):

    def __init__(self):
        super().__init__(404)


class InvalidArgument(Exception):

    def __init__(self, message: str):
        super().__init__(message)


class MessageAborted(Exception):
    def __init__(self):
        super().__init__('The message was aborted before the client sent its whole content.')
