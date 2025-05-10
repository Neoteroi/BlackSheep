from typing import Optional

from essentials.meta import deprecated

from blacksheep.messages import Request, Response
from blacksheep.server import Application


class FakeApplication(Application):
    """Application class used for testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.auto_start: bool = True
        self.request: Optional[Request] = None
        self.response: Optional[Response] = None

    @deprecated(
        "This function is not needed anymore, and will be removed. Rely instead on "
        "await app.start() or the automatic start happening on await app(...)."
    )
    def setup_controllers(self):
        pass

    async def handle(self, request):
        response = await super().handle(request)
        self.request = request
        self.response = response
        return response

    async def __call__(self, scope, receive, send):
        if not self.started and self.auto_start:
            await self.start()
        return await super().__call__(scope, receive, send)
