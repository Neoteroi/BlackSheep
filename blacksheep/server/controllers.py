from blacksheep import Request
from blacksheep.server.routing import RoutesRegistry
from typing import Optional


# singleton router used to store initial configuration, before the application starts
# this is used as *default* router for controllers, but it can be overridden - see for example tests in test_controllers
router = RoutesRegistry()


head = router.head
get = router.get
post = router.post
put = router.put
patch = router.patch
delete = router.delete
trace = router.trace
options = router.options
connect = router.connect


class ControllerMeta(type):

    def __init__(cls, name, bases, attr_dict):
        super().__init__(name, bases, attr_dict)

        for value in attr_dict.values():
            if hasattr(value, 'route_handler'):
                setattr(value, 'controller_type', cls)


class Controller(metaclass=ControllerMeta):
    """Base class for all controllers."""

    @classmethod
    def route(cls) -> Optional[str]:
        """
        The base route to be used by all request handlers defined on a controller type.
        Override this class method in subclasses, to implement base routes.
        """
        return None

    async def on_request(self, request: Request):
        """Extensibility point: controllers support executing a function at each web request.
        This method is executed before model binding happens: it is possible to read values from the request:
        headers are immediately available, and the user can decide to wait for the body (e.g. await request.json()).

        Since controllers support dependency injection, it is possible to apply logic using dependent services,
        specified in the __init__ constructor.
        """


