"""
Root module of the framework. This module re-exports the most commonly
used types to reduce the verbosity of the imports statements.
"""
__author__ = "Roberto Prevato <roberto.prevato@gmail.com>"

from neoteroi.web.contents import Content as Content
from neoteroi.web.contents import FormContent as FormContent
from neoteroi.web.contents import FormPart as FormPart
from neoteroi.web.contents import HTMLContent as HTMLContent
from neoteroi.web.contents import HtmlContent as HtmlContent
from neoteroi.web.contents import JSONContent as JSONContent
from neoteroi.web.contents import MultiPartFormData as MultiPartFormData
from neoteroi.web.contents import StreamedContent as StreamedContent
from neoteroi.web.contents import TextContent as TextContent
from neoteroi.web.contents import parse_www_form as parse_www_form
from neoteroi.web.cookies import Cookie as Cookie
from neoteroi.web.cookies import CookieSameSiteMode as CookieSameSiteMode
from neoteroi.web.cookies import (
    datetime_from_cookie_format as datetime_from_cookie_format,
)
from neoteroi.web.cookies import datetime_to_cookie_format as datetime_to_cookie_format
from neoteroi.web.cookies import parse_cookie as parse_cookie
from neoteroi.web.exceptions import HTTPException as HTTPException
from neoteroi.web.headers import Header as Header
from neoteroi.web.headers import Headers as Headers
from neoteroi.web.messages import Message as Message
from neoteroi.web.messages import Request as Request
from neoteroi.web.messages import Response as Response
from neoteroi.web.server.application import Application as Application
from neoteroi.web.server.authorization import allow_anonymous as allow_anonymous
from neoteroi.web.server.authorization import auth as auth
from neoteroi.web.server.bindings import ClientInfo as ClientInfo
from neoteroi.web.server.bindings import FromBytes as FromBytes
from neoteroi.web.server.bindings import FromCookie as FromCookie
from neoteroi.web.server.bindings import FromFiles as FromFiles
from neoteroi.web.server.bindings import FromForm as FromForm
from neoteroi.web.server.bindings import FromHeader as FromHeader
from neoteroi.web.server.bindings import FromJSON as FromJSON
from neoteroi.web.server.bindings import FromQuery as FromQuery
from neoteroi.web.server.bindings import FromRoute as FromRoute
from neoteroi.web.server.bindings import FromServices as FromServices
from neoteroi.web.server.bindings import FromText as FromText
from neoteroi.web.server.bindings import ServerInfo as ServerInfo
from neoteroi.web.server.responses import (
    ContentDispositionType as ContentDispositionType,
)
from neoteroi.web.server.responses import FileInput as FileInput
from neoteroi.web.server.responses import accepted as accepted
from neoteroi.web.server.responses import bad_request as bad_request
from neoteroi.web.server.responses import created as created
from neoteroi.web.server.responses import file as file
from neoteroi.web.server.responses import forbidden as forbidden
from neoteroi.web.server.responses import html as html
from neoteroi.web.server.responses import json as json
from neoteroi.web.server.responses import moved_permanently as moved_permanently
from neoteroi.web.server.responses import no_content as no_content
from neoteroi.web.server.responses import not_found as not_found
from neoteroi.web.server.responses import not_modified as not_modified
from neoteroi.web.server.responses import ok as ok
from neoteroi.web.server.responses import permanent_redirect as permanent_redirect
from neoteroi.web.server.responses import pretty_json as pretty_json
from neoteroi.web.server.responses import redirect as redirect
from neoteroi.web.server.responses import see_other as see_other
from neoteroi.web.server.responses import status_code as status_code
from neoteroi.web.server.responses import temporary_redirect as temporary_redirect
from neoteroi.web.server.responses import text as text
from neoteroi.web.server.responses import unauthorized as unauthorized
from neoteroi.web.server.routing import Route as Route
from neoteroi.web.server.routing import RouteException as RouteException
from neoteroi.web.server.routing import Router as Router
from neoteroi.web.server.routing import RoutesRegistry as RoutesRegistry
from neoteroi.web.server.websocket import WebSocket as WebSocket
from neoteroi.web.server.websocket import (
    WebSocketDisconnectError as WebSocketDisconnectError,
)
from neoteroi.web.server.websocket import WebSocketError as WebSocketError
from neoteroi.web.server.websocket import WebSocketState as WebSocketState
from neoteroi.web.url import URL as URL
from neoteroi.web.url import InvalidURL as InvalidURL
