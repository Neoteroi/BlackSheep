from typing import List, Optional, Sequence

from blacksheep.exceptions import BadRequest
from blacksheep.messages import Request


class InvalidHostError(BadRequest):
    def __init__(self, host_value: str):
        super().__init__(f"Invalid host: {host_value}.")
        self.host = host_value


class TrustedHostsMiddleware:
    def __init__(
        self,
        allowed_hosts: Optional[Sequence[str]] = None,
    ) -> None:
        self.allowed_hosts: List[str] = list(allowed_hosts) if allowed_hosts else []

    def is_valid_host(self, host: str) -> bool:
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            return True
        return host in self.allowed_hosts

    def validate_host(self, host: str) -> None:
        if not self.is_valid_host(host):
            raise InvalidHostError(host)

    async def __call__(self, request: Request, handler):
        self.validate_host(request.host)
        return await handler(request)
