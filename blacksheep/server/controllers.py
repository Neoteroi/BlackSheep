from blacksheep import Request
from blacksheep.server.routing import Router


router = Router()  # singleton router used to store initial configuration, before the application starts


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
    """Base class for controller types"""

    async def on_request(self, request: Request):
        ...

