from typing import Optional

from blacksheep.messages import Request, Response
from blacksheep.server import Application


class FakeApplication(Application):
    def __init__(self, *args, **kwargs):
        super().__init__(show_error_details=True, *args, **kwargs)
        self.request: Optional[Request] = None
        self.response: Optional[Response] = None

    def normalize_handlers(self):
        if self._service_provider is None:
            self.build_services()
        super().normalize_handlers()

    def setup_controllers(self):
        self.use_controllers()
        self.build_services()
        self.normalize_handlers()

    async def handle(self, request):
        response = await super().handle(request)
        self.request = request
        self.response = response
        return response

    def prepare(self):
        self.normalize_handlers()
        self.configure_middlewares()
