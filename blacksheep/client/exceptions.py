from blacksheep import URL


class InvalidResponseException(Exception):

    def __init__(self, message, response):
        super().__init__(message)
        self.response = response


class MissingLocationForRedirect(InvalidResponseException):

    def __init__(self, response):
        super().__init__(f'The server returned a redirect status ({response.status}) '
                         f'but didn`t send a "Location" header', response)


class RequestException(Exception):

    def __init__(self, message, allow_retry):
        super().__init__(message)
        self.can_retry = allow_retry


class ConnectionTimeout(TimeoutError):
    def __init__(self, url: URL, timeout: float):
        super().__init__(f'Connection attempt timed out, to {url.value.decode()}. Current timeout setting: {timeout}.')


class RequestTimeout(TimeoutError):
    def __init__(self, url: URL, timeout: float):
        super().__init__(f'Request timed out, to: {url.value.decode()}. Current timeout setting: {timeout}.')


class CircularRedirectError(InvalidResponseException):

    def __init__(self, path, response):
        path_string = ' --> '.join(x.decode('utf8') for x in path)
        super().__init__(f'Circular redirects detected. Requests path was: ({path_string}).', response)


class MaximumRedirectsExceededError(InvalidResponseException):

    def __init__(self, path, response, maximum_redirects):
        path_string = ', '.join(x.decode('utf8') for x in path)
        super().__init__(f'Maximum Redirects Exceeded ({maximum_redirects}). Requests path was: ({path_string}).',
                         response)


class UnsupportedRedirect(Exception):
    """Exception risen when the client cannot handle a redirect;
    for example if the redirect is to a URN (not a URL). In such case,
    we don't follow the redirect and return the response with location: the caller
    can handle it."""
