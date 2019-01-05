__author__ = 'Roberto Prevato <roberto.prevato@gmail.com>'


from .url import URL, InvalidURL
from .headers import Header, Headers
from .exceptions import HttpException
from .contents import (Content,
                       JsonContent,
                       FormContent,
                       FormPart,
                       TextContent,
                       HtmlContent,
                       MultiPartFormData,
                       parse_www_form)
from .cookies import Cookie, datetime_from_cookie_format, datetime_to_cookie_format, parse_cookie
from .messages import Request, Response


class HttpMethod:
    GET = b'GET'
    HEAD = b'HEAD'
    POST = b'POST'
    PUT = b'PUT'
    DELETE = b'DELETE'
    TRACE = b'TRACE'
    OPTIONS = b'OPTIONS'
    CONNECT = b'CONNECT'
    PATCH = b'PATCH'
