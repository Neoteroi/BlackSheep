"""
See "Model Binding" in ASP.NET Core
https://docs.microsoft.com/en-us/aspnet/core/mvc/models/model-binding?view=aspnetcore-2.2
"""
from typing import Generic, TypeVar
from inspect import Signature, Parameter


SimpleType = TypeVar('SimpleType', str, int, float)
ParamType = TypeVar('ParamType')


class FromBody(Generic[ParamType]):
    """Annotates an input parameter that is expected to come from request body."""


    def __init__(self, value=None):
        self.value = value


class FromBodyAlt:

    def __init__(self, expected_type: Generic[ParamType]):
        self.expected_type = expected_type


class FromJson(Generic[ParamType]):
    """pass"""


class FromXml(Generic[ParamType]):
    """pass"""


class FromHeader(Generic[SimpleType]):
    """Annotates an input parameter that is expected to come from request headers."""


class FromQuery(Generic[SimpleType]):
    """Annotates an input parameter that is expected to come from request query string."""


class FromRoute(Generic[SimpleType]):
    """Annotates an input parameter that is expected to come from request path (route)."""


class FromServices(Generic[ParamType]):
    """Annotates an input parameter that is bound from application services (DI)."""


def example_header(xxx: FromHeader[str]):
    pass


class Item:

    def __init__(self, a, b):
        self.a = a
        self.b = b


class Cat:
    pass


def example(param: FromBody[Item],
            x: FromBodyAlt(Cat)):  # TO differentiate between services to inject from app.services and body parameters
    print(param)
    print(x)


def a(param: Item):
    print(param)


if __name__ == '__main__':
    print(example)

    for m in (example, a):
        sig = Signature.from_callable(m)
        params = sig.parameters

        for param_name, param_value in params.items():
            annotation = param_value.annotation

            try:
                origin = annotation.__origin__
            except AttributeError:
                print('Non generic type, so this should be a service')
                pass
            else:
                if origin is FromBody:
                    expected_type = annotation.__args__[0]

                    # TODO: define extractor that reads JSON or XML and creates an instance of expected type;
                    #       raise exception if it is not found

                    print('Expected type:', expected_type)

                    # TODO: read JSON or XML from request body (or only JSON?)
