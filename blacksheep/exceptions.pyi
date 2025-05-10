from typing import Optional

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

class Conflict(HTTPException):
    def __init__(self, message: str = "Conflict"):
        super().__init__(409, message)

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
    def __init__(
        self,
        message: str = "Internal Server Error",
        source_error: Optional[Exception] = None,
    ):
        super().__init__(500, message)
        self.source_error = source_error

class NotImplementedByServer(HTTPException):
    def __init__(self, message: str = "Not Implemented"):
        super().__init__(501, message)

class FailedRequestError(HTTPException):
    def __init__(self, status: int, data: str) -> None:
        super().__init__(
            status,
            f"The response status code does not indicate success: {status}. Response body: {data}",
        )
        self.data = data
