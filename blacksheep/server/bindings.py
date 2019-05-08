from typing import Type
from blacksheep import Request
from blacksheep.exceptions import BadRequest


class FromBody:

    def __init__(self,
                 expected_type: Type,
                 required: bool = False,
                 accept_json: bool = True,
                 accept_xml: bool = True):
        self.expected_type = expected_type
        self.required = required
        self.accept_json = accept_json
        self.accept_xml = accept_xml

    async def get_json_value(self, request: Request):
        data = await request.json()

        try:
            return self.expected_type(**data)
        except TypeError as te:
            # TODO: log this error maybe
            # TODO: '__init__() got an unexpected keyword argument \'c\'' maybe should be ignored!
            raise BadRequest('Invalid request body')

    async def get_xml_value(self, request: Request):
        pass

    async def get_value(self, request: Request):

        if request.declares_json():
            return await self.get_json_value(request)

        if request.declares_xml():
            return await self.get_xml_value(request)

        return None
