from blacksheep import Request
from blacksheep.server.routing import Router


# singleton router used to store initial configuration, before the application starts
# this is used as *default* router for controllers, but it can be overridden - see for example tests in test_controllers
router = Router()


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
    """Base class for all controller"""

    async def on_request(self, request: Request):
        """Extensibility point: controllers support executing a function at each web request.
        This method is executed before model binding happens: it is possible to read values from the request:
        headers are immediately available, and the user can decide to wait for the body (e.g. await request.json()).

        Since controllers support dependency injection, it is possible to apply logic using dependent services,
        specified in the __init__ constructor.
        """

