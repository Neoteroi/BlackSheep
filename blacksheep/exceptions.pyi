class InvalidOperation(Exception):
    def __init__(self, message: str, inner_exception: object = None):
        super().__init__(message)
        self.inner_exception = inner_exception

class HTTPException(Exception):
    def __init__(self, status: int, message: str = "HTTP Exception"):
        super().__init__(message)
        self.status = status

class BadRequest(HTTPException):
    def __init__(self, message: str):
        super().__init__(400, message)

class Unauthorized(HTTPException):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(401, message)

class Forbidden(HTTPException):
    def __init__(self, message: str = "Forbidden"):
        super().__init__(403, message)

class BadRequestFormat(BadRequest):
    def __init__(self, message: str, inner_exception: object = None):
        super().__init__(message)
        self.inner_exception = inner_exception

class RangeNotSatisfiable(HTTPException):
    def __init__(self, message: str = "Range Not Satisfiable"):
        super().__init__(416, message)

class NotFound(HTTPException):
    def __init__(self):
        super().__init__(404)

class InvalidArgument(Exception):
    def __init__(self, message: str):
        super().__init__(message)

class MessageAborted(Exception):
    def __init__(self):
        super().__init__(
            "The message was aborted before the client sent its whole content."
        )

class InternalServerError(HTTPException):
    def __init__(self, message: str = "Internal Server Error"):
        super().__init__(500, message)

class NotImplementedByServer(HTTPException):
    def __init__(self, message: str = "Not Implemented"):
        super().__init__(501, message)
