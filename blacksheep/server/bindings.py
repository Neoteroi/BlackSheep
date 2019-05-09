from abc import ABC, abstractmethod
from typing import TypeVar, Optional, Callable, List
from urllib.parse import unquote
from blacksheep import Request
from blacksheep.exceptions import BadRequest


T = TypeVar('T')


def _generalize_init_type_error_message(ex: TypeError) -> str:
    return str(ex)\
        .replace('__init__() ', '')\
        .replace('keyword argument', 'parameter') \
        .replace('keyword arguments', 'parameters') \
        .replace('positional arguments', 'parameters')\
        .replace('positional argument', 'parameter')


class Binder(ABC):

    def __init__(self,
                 expected_type: T,
                 required: bool = True,
                 converter: Optional[Callable] = None):
        self.expected_type = expected_type
        self.required = required
        self.converter = converter

    @abstractmethod
    async def get_value(self, request: Request) -> T:
        pass


class MissingBodyError(BadRequest):

    def __init__(self):
        super().__init__('Missing body payload')


class MissingParameterError(BadRequest):

    def __init__(self, name: str, source: str):
        super().__init__(f'Missing parameter `{name}` from {source}')


class InvalidRequestBody(BadRequest):

    def __init__(self, description: Optional[str] = 'Invalid body payload'):
        super().__init__(description)


class FromJson(Binder):

    def __init__(self,
                 expected_type: T,
                 required: bool = False,
                 converter: Optional[Callable] = None
                 ):
        super().__init__(expected_type, required, converter)

    def parse_value(self, data: dict) -> T:
        try:
            if self.converter:
                return self.converter(data)

            return self.expected_type(**data)
        except TypeError as te:
            raise InvalidRequestBody(_generalize_init_type_error_message(te))
        except ValueError as ve:
            raise InvalidRequestBody(str(ve))

    async def get_value(self, request: Request) -> T:
        if request.declares_json():
            data = await request.json()

            if not data:
                raise MissingBodyError()

            return self.parse_value(data)

        if self.required:
            if not request.has_body():
                raise MissingBodyError()

            raise InvalidRequestBody('Expected JSON payload')

        return None


class FromHeader(Binder):

    def __init__(self,
                 name: bytes,
                 expected_type: T,
                 required: bool = False,
                 converter: Optional[Callable] = None):
        super().__init__(expected_type, required, converter)
        self.name = name

    def parse_value(self, value: List[bytes]) -> T:
        if not value:
            return None

        if self.converter:
            return self.converter(value)

        # TODO: unquote the value because it's more user-friendly
        # TODO: support list of strings and unquote them
        if self.expected_type is str:
            return value[0].decode()

        if self.expected_type is bytes:
            return value[0]

        if isinstance(value, type(self.expected_type)):
            return value

    async def get_value(self, request: Request) -> T:
        headers = request.headers[self.name]

        value = self.parse_value([header.value for header in headers])

        if not value:
            if self.required:
                raise MissingParameterError(self.name.decode(), 'header')
            return None

        return value
