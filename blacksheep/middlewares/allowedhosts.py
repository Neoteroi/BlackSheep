from typing import Awaitable, Callable, List, Optional, Sequence

from blacksheep import Request, Response
from blacksheep.server.responses import text

ENFORCE_DOMAIN_WILDCARD = "Domain wildcard patterns must be like '*.example.com'."


class AllowedHostsMiddleware:

    def __init__(
            self,
            allowed_hosts: Sequence[str] = None,
    ) -> None:
        self._allowed_hosts = None
        self.allowed_hosts = allowed_hosts

    @property
    def allow_any(self) -> bool:
        return "*" in self.allowed_hosts

    @property
    def allowed_hosts(self) -> List[str]:
        return self._allowed_hosts

    @allowed_hosts.setter
    def allowed_hosts(self, value: Optional[Sequence[str]] = None) -> None:
        if value:
            self._validate_allowed_hosts(value)
        else:
            value = ["*"]
        self._allowed_hosts = list(value)

    def _validate_allowed_hosts(self, value: Sequence[str]) -> None:
        for pattern in value:
            assert "*" not in pattern[1:], ENFORCE_DOMAIN_WILDCARD
            if pattern.startswith("*") and pattern != "*":
                assert pattern.startswith("*."), ENFORCE_DOMAIN_WILDCARD

    def is_valid_host(self, host: str) -> bool:
        for pattern in self.allowed_hosts:
            if host == pattern or (
                pattern.startswith("*") and host.endswith(pattern[1:])
            ):
                return True
        return False

    async def __call__(self,
                       request: Request,
                       handler: Callable[[Request], Awaitable[Response]]
                       ) -> Response:
        host = request.headers.get_single(b"host").decode("utf-8").split(":")[0]

        if self.is_valid_host(host):
            response = await handler(request)
        else:
            response = text("Invalid host header", status=400)
        return response