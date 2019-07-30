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
    GET = 'GET'
    HEAD = 'HEAD'
    POST = 'POST'
    PUT = 'PUT'
    DELETE = 'DELETE'
    TRACE = 'TRACE'
    OPTIONS = 'OPTIONS'
    CONNECT = 'CONNECT'
    PATCH = 'PATCH'
