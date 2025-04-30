from typing import Optional

from blacksheep.messages import Request, Response
from blacksheep.server import Application


class FakeApplication(Application):
    """Application class used for testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request: Optional[Request] = None
        self.response: Optional[Response] = None

    def normalize_handlers(self):
        super().normalize_handlers()

    def setup_controllers(self):
        self.use_controllers()
        self.normalize_handlers()

    async def handle(self, request):
        response = await super().handle(request)
        self.request = request
        self.response = response
        return response

    def prepare(self):
        self.normalize_handlers()
        self.configure_middlewares()
