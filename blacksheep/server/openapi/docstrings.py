"""
This module implements classes and methods for **BASIC** parsing of docstrings, to
obtain some information, such as parameters descriptions, that can be used for
OpenAPI Documentation. The framework also provides the possibility to control the docs
configuration directly: if simple parsing doesn't work, the user should use the @docs
decorator.

See
* https://www.neoteroi.dev/blacksheep/openapi/
* http://epydoc.sourceforge.net/manual-epytext.html#the-epytext-markup-language
* tests/test_openapi_docstrings.py

These are not meant to be a complete parsing solution, that would be worth a whole
library by itself.
"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from textwrap import dedent
from typing import Any, Dict, Optional, Sequence, Type
from uuid import UUID

from .common import ParameterInfo


@dataclass
class DocstringInfo:
    summary: str
    description: str
    parameters: Dict[str, ParameterInfo]
    return_type: Optional[Type] = None
    return_description: Optional[str] = None


def _ensure_docstring(value: str) -> None:
    if not value:
        raise ValueError("Missing docstring")


class DocstringDialect(ABC):
    @abstractmethod
    def is_match(self, docstring: str) -> bool:
        ...

    @abstractmethod
    def parse_docstring(self, docstring: str) -> DocstringInfo:
        ...


_TYPE_REPRS = {
    "number": float,
    "integer": int,
    "int": int,
    "float": float,
    "date": date,
    "datetime": datetime,
    "uuid": UUID,
    "guid": UUID,
}


def _type_repr_to_type(type_repr: str) -> Type:
    if type_repr in _TYPE_REPRS:
        return _TYPE_REPRS[type_repr]
    return str


def _collapse(value: str) -> str:
    return " ".join(dedent(value).split())


def _handle_type_repr(parameter_info: ParameterInfo, type_repr: str) -> None:
    if " or None" in type_repr or type_repr.endswith("?"):
        parameter_info.required = False
        type_repr = type_repr.replace(" or None", "").replace("?", "")
    parameter_info.value_type = _type_repr_to_type(type_repr)


@dataclass
class PatternsDocstringDialectOptions:
    description_rx: re.Pattern
    return_rx: re.Pattern
    return_type_rx: re.Pattern
    param_rx: re.Pattern
    param_type_rx: re.Pattern


class PatternsDocstringDialect(DocstringDialect):
    def __init__(self, options: PatternsDocstringDialectOptions) -> None:
        super().__init__()
        self._options = options

    def parse_docstring(self, docstring: str) -> DocstringInfo:
        parameters: Dict[str, ParameterInfo] = {}
        types: Dict[str, Any] = {}
        return_description = None

        docstring = dedent(docstring).strip("\n")

        for m in self._options.param_rx.finditer(docstring):
            param_name = m.group("param_name").strip()

            if " " in param_name:
                # handle optional type in the param_name, like:
                # @param int foo:
                # @param int or None foo:

                (*type_parts, name) = param_name.split(" ")
                types[name] = " ".join(type_parts)
                param_name = name

            parameters[param_name] = ParameterInfo(
                description=_collapse(m.group("param_desc"))
            )

        for m in self._options.param_type_rx.finditer(docstring):
            types[m.group("param_name").strip()] = m.group("type_repr").strip()

        for key, value in types.items():
            if key in parameters:
                parameter_info = parameters[key]
                _handle_type_repr(parameter_info, value)

        m = self._options.return_rx.search(docstring)
        if m:
            return_description = m.group("description")

        m = self._options.return_type_rx.search(docstring)
        if m:
            return_type = _type_repr_to_type(m.group("type_repr").strip())
        else:
            return_type = None

        description_m = self._options.description_rx.match(docstring)

        if description_m:
            description = description_m.group("description").strip()
        else:
            description = ""

        if "\n\n" in description:
            summary = description.split("\n\n")[0]
        else:
            summary = description

        return DocstringInfo(
            summary=_collapse(summary),
            description=_collapse(description),
            parameters=parameters,
            return_type=return_type,
            return_description=_collapse(return_description)
            if return_description
            else None,
        )


class EpytextDialect(PatternsDocstringDialect):
    def __init__(
        self, options: Optional[PatternsDocstringDialectOptions] = None
    ) -> None:
        super().__init__(options or self._default_options)

    _default_options = PatternsDocstringDialectOptions(
        description_rx=re.compile(r"^(?P<description>[^\@]+)"),
        return_rx=re.compile(r"@return:\s*(?P<description>[^\@]+)"),
        return_type_rx=re.compile(r"@rtype:\s*(?P<type_repr>[^\@]+)"),
        param_rx=re.compile(
            r"@param\s(?P<param_name>[^\:]+):\s*(?P<param_desc>[^\@]+)"
        ),
        param_type_rx=re.compile(
            r"@type\s*(?P<param_name>[^\:]+):\s*(?P<type_repr>[^\@]+)"
        ),
    )

    def is_match(self, docstring: str) -> bool:
        return "@param" in docstring


class ReStructuredTextDialect(PatternsDocstringDialect):
    def __init__(
        self, options: Optional[PatternsDocstringDialectOptions] = None
    ) -> None:
        super().__init__(options or self._default_options)

    _default_options = PatternsDocstringDialectOptions(
        description_rx=re.compile(r"^(?P<description>[^\:]+)"),
        return_rx=re.compile(r":return:\s*(?P<description>[^\:]+)"),
        return_type_rx=re.compile(r":rtype:\s*(?P<type_repr>[^\:]+)"),
        param_rx=re.compile(
            r":param\s(?P<param_name>[^\:]+):\s*(?P<param_desc>[^\:]+)"
        ),
        param_type_rx=re.compile(
            r":type\s*(?P<param_name>[^\:]+):\s*(?P<type_repr>[^\:]+)"
        ),
    )

    def is_match(self, docstring: str) -> bool:
        return ":param" in docstring


class NumpydocDialect(DocstringDialect):
    def is_match(self, docstring: str) -> bool:
        return "Parameters" in docstring

    def parse_docstring(self, docstring: str) -> DocstringInfo:
        ...


class GoogleDocDialect(DocstringDialect):
    def is_match(self, docstring: str) -> bool:
        return "Args:" in docstring

    def parse_docstring(self, docstring: str) -> DocstringInfo:
        ...


default_dialects = [
    EpytextDialect(),
    ReStructuredTextDialect(),
    NumpydocDialect(),
    GoogleDocDialect(),
]


def parse_docstring(
    docstring: str,
    dialects: Optional[Sequence[DocstringDialect]] = None,
) -> DocstringInfo:
    _ensure_docstring(docstring)

    if not dialects:
        dialects = default_dialects

    for dialect in dialects:
        if dialect.is_match(docstring):
            # use this dialect to extract available
            # information from the docstring
            ...

    raise Exception("Not implemented")
