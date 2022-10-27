from abc import ABC, abstractmethod
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address
from typing import AnyStr, Iterable, List, Optional, Sequence, Union

from blacksheep.exceptions import BadRequest
from blacksheep.headers import Headers
from blacksheep.messages import Request

from .hosts import TrustedHostsMiddleware

IPAddress = Union[IPv4Address, IPv6Address]
IPNetwork = Union[IPv4Network, IPv6Network]


class TooManyHeaders(BadRequest):
    def __init__(self, header_name: bytes):
        super().__init__(f"Too many {header_name.decode()} headers.")
        self.header_name = header_name.decode()


class TooManyForwardValues(BadRequest):
    def __init__(self, count: int):
        super().__init__(f"Too many forward values: {count}.")


class InvalidProxyIPError(BadRequest):
    def __init__(self, proxy_ip: IPAddress):
        super().__init__(f"Proxy IP not recognized: {proxy_ip}")


class BaseForwardedHeadersMiddleware(TrustedHostsMiddleware, ABC):
    def __init__(
        self,
        allowed_hosts: Optional[Sequence[str]] = None,
        known_proxies: Optional[Sequence[IPAddress]] = None,
        known_networks: Optional[Sequence[IPNetwork]] = None,
        forward_limit: int = 1,
        accept_only_proxied_requests: bool = True,
    ) -> None:
        super().__init__(allowed_hosts)
        self.known_proxies: List[IPAddress] = (
            list(known_proxies) if known_proxies else [ip_address("127.0.0.1")]
        )
        self.known_networks: List[IPNetwork] = (
            list(known_networks) if known_networks else []
        )
        self.accept_only_proxied_requests = accept_only_proxied_requests
        self.forward_limit = forward_limit

    def parse_ip(self, value: str) -> IPAddress:
        return ip_address(value)

    def should_validate_client_ip(self) -> bool:
        """
        Returns a value indicating whether the request client ip should be validated.

        If known proxies or known networks are configured, and
        `accept_only_proxied_requests` is enabled, then the web framework accepts only
        requests that are proxied.

        If `accept_only_proxied_requests` is set to False, it means the server will
        acceptd both requests that are proxied and requests that are hitting the web
        server directly.
        """
        return (
            self.accept_only_proxied_requests
            and any(self.known_proxies)
            or any(self.known_networks)
        )

    def validate_proxy_ip(self, proxy_ip: IPAddress) -> None:
        if self.known_proxies:
            if proxy_ip in self.known_proxies:
                return

        if self.known_networks:
            if any(network for network in self.known_networks if proxy_ip in network):
                return

        raise InvalidProxyIPError(proxy_ip)

    def validate_proxies_ips(self, proxies: List[IPAddress]) -> None:
        for proxy_ip in proxies:
            self.validate_proxy_ip(proxy_ip)

    @abstractmethod
    async def __call__(self, request: Request, handler):
        """Middleware callback."""


class ForwardedHeaderEntry:
    def __init__(
        self,
        forwarded_for: str,
        forwarded_by: str = "",
        forwarded_host: str = "",
        forwarded_proto: str = "",
    ):
        self.forwarded_for = forwarded_for
        self.forwarded_by = forwarded_by
        self.forwarded_host = forwarded_host
        self.forwarded_proto = forwarded_proto

    def __eq__(self, o: object) -> bool:
        if isinstance(o, ForwardedHeaderEntry):
            return self.__dict__ == o.__dict__
        if isinstance(o, dict):
            return self.__dict__ == o
        return False


def _strip_chars(value):
    return value.strip('"[').replace("]", "")


def parse_forwarded_header(header_value: AnyStr) -> Iterable[ForwardedHeaderEntry]:
    if isinstance(header_value, bytes):
        value = header_value.decode()
    else:
        value = header_value

    groups = value.split(",")

    for group in groups:
        group = group.strip()
        directives = group.split(";")

        forwarded_for: str = ""
        forwarded_by: str = ""
        forwarded_host: str = ""
        forwarded_proto: str = ""

        for directive in directives:
            directive = directive.strip()

            if directive.lower().startswith("for="):
                forwarded_for = _strip_chars(directive[4:])

            if directive.lower().startswith("by="):
                forwarded_by = _strip_chars(directive[3:])

            if directive.lower().startswith("host="):
                forwarded_host = _strip_chars(directive[5:])

            if directive.lower().startswith("proto="):
                forwarded_proto = _strip_chars(directive[6:])

        yield ForwardedHeaderEntry(
            forwarded_for, forwarded_by, forwarded_host, forwarded_proto
        )


class ForwardedHeadersMiddleware(BaseForwardedHeadersMiddleware):
    """
    Class that handles the standard Forwarded header. This middleware should be
    configured early in the chain of middlewares, as it validates and updates each
    request to apply the proper protocol, host, and client ip information.
    """

    def __init__(
        self,
        allowed_hosts: Optional[Sequence[str]] = None,
        known_proxies: Optional[Sequence[IPAddress]] = None,
        known_networks: Optional[Sequence[IPNetwork]] = None,
        forward_limit: int = 1,
        accept_only_proxied_requests: bool = True,
    ) -> None:
        super().__init__(
            allowed_hosts,
            known_proxies,
            known_networks,
            forward_limit=forward_limit,
            accept_only_proxied_requests=accept_only_proxied_requests,
        )

    def get_forwarded_values(self, headers: Headers) -> Iterable[ForwardedHeaderEntry]:
        forwarded_headers = headers[b"Forwarded"]

        for header in forwarded_headers:
            yield from parse_forwarded_header(header)

    def validate_forwarded_entries(
        self, entries: Sequence[ForwardedHeaderEntry]
    ) -> None:
        if len(entries) > self.forward_limit:
            raise TooManyForwardValues(len(entries))

        for entry in entries:
            if entry.forwarded_host:
                self.validate_host(entry.forwarded_host)

            if entry.forwarded_by:
                # the value can be an IP address, but it does not have to;
                # it can be any string
                # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Forwarded
                try:
                    ip = ip_address(entry.forwarded_by)
                except ValueError:
                    pass
                else:
                    self.validate_proxy_ip(ip)

    async def __call__(self, request: Request, handler):
        # Forwarded: by=<identifier>;for=<identifier>;host=<host>;proto=<http|https>
        if self.should_validate_client_ip():
            self.validate_proxy_ip(ip_address(request.client_ip))

        forwarded_entries = list(self.get_forwarded_values(request.headers))

        if forwarded_entries:
            self.validate_forwarded_entries(forwarded_entries)
            first_entry = forwarded_entries[0]

            if first_entry.forwarded_host:
                request.host = first_entry.forwarded_host

            if first_entry.forwarded_proto:
                request.scheme = first_entry.forwarded_proto

            if first_entry.forwarded_for:
                # Note: if the proxy server is configured to send an obfuscated
                # identifier, like "_hidden", we set it here anyway
                request.original_client_ip = first_entry.forwarded_for

        return await handler(request)


class XForwardedHeadersMiddleware(BaseForwardedHeadersMiddleware):
    """
    Class that handles the de-facto standard X-Forwarded headers. This middleware should
    be configured early in the chain of middlewares, as it validates and updates each
    request to apply the proper protocol, host, and client ip information.
    """

    def __init__(
        self,
        allowed_hosts: Optional[Sequence[str]] = None,
        known_proxies: Optional[Sequence[IPAddress]] = None,
        known_networks: Optional[Sequence[IPNetwork]] = None,
        forward_limit: int = 1,
        accept_only_proxied_requests: bool = True,
    ) -> None:
        """
        Creates a new instance of XForwardedHeadersMiddleware which handles X-Forwarded
        headers. By default only 1 forward level is enabled (this can be increased using
        `forward_limit` option. It is possible to change the names of the headers
        that are handled by this class (by default X-Forwarded-For/Host/Proto).
        Requests are updated by this middleware to expose information about the original
        client, which is useful in some circumstances, such as recreating the original
        URL of the request.

        Parameters
        ----------
        allowed_hosts : Optional[Sequence[str]], optional
            If provided, enables validation of the request's direct host value and of
            forwarded-host header values, by default None
        known_proxies : Optional[Sequence[IPAddress]], optional
            If provided, enables validation of proxy IP addresses through IP list
            configuration, by default None
        known_networks : Optional[Sequence[IPNetwork]], optional
            If provided, enables validation of proxy IP addresses through networks
            configuration, by default None
        forward_limit : int, optional
            The maximum number of forwards that are allowed. By default 1
        """
        super().__init__(
            allowed_hosts,
            known_proxies,
            known_networks,
            forward_limit=forward_limit,
            accept_only_proxied_requests=accept_only_proxied_requests,
        )
        self.forwarded_for_header_name = b"X-Forwarded-For"
        self.forwarded_host_header_name = b"X-Forwarded-Host"
        self.forwarded_proto_header_name = b"X-Forwarded-Proto"

    def get_forwarded_for(self, headers: Headers) -> List[IPAddress]:
        # X-Forwarded-For: <client>, <proxy1>, <proxy2>
        forwarded_for_headers: List[bytes] = list(
            headers[self.forwarded_for_header_name]
        )

        if not forwarded_for_headers:
            return []

        if len(forwarded_for_headers) > 1:
            raise TooManyHeaders(self.forwarded_for_header_name)

        forwarded_for = forwarded_for_headers[0].decode().split(",")
        return [
            self.parse_ip(addr) for addr in (a.strip() for a in forwarded_for) if addr
        ]

    def get_forwarded_proto(self, headers: Headers) -> List[str]:
        # X-Forwarded-Proto: https
        forwarded_proto_headers: List[bytes] = list(
            headers[self.forwarded_proto_header_name]
        )

        if not forwarded_proto_headers:
            return []

        if len(forwarded_proto_headers) > 1:
            raise TooManyHeaders(self.forwarded_proto_header_name)

        forwarded_proto = forwarded_proto_headers[0].decode().split(",")
        return [p.strip() for p in forwarded_proto]

    def get_forwarded_host(self, headers: Headers) -> Optional[str]:
        # X-Forwarded-Host: id42.example-cdn.com
        # original host requested by the client in the Host HTTP request header.
        forwarded_hosts = headers[self.forwarded_host_header_name]

        if not forwarded_hosts:
            return None

        if len(forwarded_hosts) > 1:
            raise TooManyHeaders(self.forwarded_host_header_name)

        return forwarded_hosts[0].decode()

    def validate_forwarded_for(self, values: List[IPAddress]) -> None:
        if len(values) > self.forward_limit:
            raise TooManyForwardValues(len(values))

        # the first value is the ID of the client - that is valid
        _, *proxies = values

        self.validate_proxies_ips(proxies)

    def validate_forwarded_proto(self, values: List[str]) -> None:
        if len(values) > self.forward_limit:
            raise TooManyForwardValues(len(values))

    async def __call__(self, request: Request, handler):
        if self.should_validate_client_ip():
            self.validate_proxy_ip(ip_address(request.client_ip))

        headers = request.headers
        forwarded_for = self.get_forwarded_for(headers)
        forwarded_host = self.get_forwarded_host(headers)
        forwarded_proto = self.get_forwarded_proto(headers)

        if forwarded_host:
            self.validate_host(forwarded_host)

            request.host = forwarded_host
        else:
            # validate the host from the Host header anyway
            self.validate_host(request.host)

        if forwarded_for:
            self.validate_forwarded_for(forwarded_for)

            request.original_client_ip = str(forwarded_for[0])

        if forwarded_proto:
            self.validate_forwarded_proto(forwarded_proto)

            request.scheme = forwarded_proto[0]

        return await handler(request)
