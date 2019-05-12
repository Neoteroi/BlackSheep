import inspect
from typing import Union, List, TypeVar, Callable
from inspect import Signature, Parameter, _empty
from .bindings import FromHeader, FromJson, FromQuery, FromRoute, FromServices, Binder, SyncBinder, FromBody


class MultipleFromBodyBinders(Exception):

    def __init__(self, method, first_match, new_match):
        super().__init__(f'Cannot use more than one `FromBody` binder for the same method ({method.__name__}). '
                         f'The first match was: {first_match}, a second one {new_match}.'
                         )


def get_from_body_parameter(method) -> FromBody:
    """Extracts a single FromBody parameter from the given signature,
    throwing exception if more than one is defined."""
    sig = Signature.from_callable(method)

    from_body_parameter = None

    for name, parameter in sig.parameters.items():
        if isinstance(parameter.annotation, FromBody):
            if from_body_parameter is None:
                from_body_parameter = parameter.annotation
            else:
                raise MultipleFromBodyBinders(method, from_body_parameter, parameter)

    return from_body_parameter


def normalize_handler(services, method):
    sig = Signature.from_callable(method)
    params = sig.parameters
    params_len = len(params)

    #if inspect.iscoroutinefunction(method):
    #    return get_async_wrapper(services, method, params, params_len)

    #return get_sync_wrapper(services, method, params, params_len)