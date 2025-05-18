class InvalidOperation(Exception):
    def __init__(self, message: str, inner_exception=None):
        super().__init__(message)
        self.inner_exception = inner_exception


class HTTPException(Exception):
    def __init__(self, status: int, message: str = "HTTP exception"):
        super().__init__(message)
        self.status = status


class BadRequest(HTTPException):
    def __init__(self, message=None):
        super().__init__(400, message or "Bad request")


class BadRequestFormat(BadRequest):
    def __init__(self, message: str, inner_exception=None):
        super().__init__(message)
        self.inner_exception = inner_exception


class FailedRequestError(HTTPException):
    def __init__(self, status: int, data: str) -> None:
        super().__init__(
            status,
            f"The response status code does not indicate success: {status}. "
            "Response body: {data}",
        )
        self.data = data


class NotFound(HTTPException):
    def __init__(self, message=None):
        super().__init__(404, message or "Not found")


class Unauthorized(HTTPException):
    def __init__(self, message=None):
        super().__init__(401, message or "Unauthorized")


class Forbidden(HTTPException):
    def __init__(self, message=None):
        super().__init__(403, message or "Forbidden")


class Conflict(HTTPException):
    def __init__(self, message=None):
        super().__init__(409, message or "Conflict")


class RangeNotSatisfiable(HTTPException):
    def __init__(self):
        super().__init__(416, "Range not satisfiable")


class InternalServerError(HTTPException):
    def __init__(self, source_error: Exception = None):
        super().__init__(500, "Internal server error")
        self.source_error = source_error


class NotImplementedByServer(HTTPException):
    def __init__(self):
        super().__init__(501, "Not implemented by server")


class InvalidArgument(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class MessageAborted(Exception):
    def __init__(self):
        super().__init__(
            "The message was aborted before the client sent its whole content."
        )
