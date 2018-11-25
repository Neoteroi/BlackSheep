__author__ = 'Roberto Prevato <roberto.prevato@gmail.com>'


from .headers import HttpHeader, HttpHeaderCollection
from .contents import (HttpContent,
                       JsonContent,
                       FormContent,
                       TextContent,
                       HtmlContent,
                       MultiPartFormData,
                       parse_www_form)
from .cookies import HttpCookie, datetime_from_cookie_format, datetime_to_cookie_format, parse_cookie
from .messages import HttpRequest, HttpResponse


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
