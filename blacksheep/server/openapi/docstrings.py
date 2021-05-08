"""
This module implements classes and methods for **BASIC** parsing of docstrings, to
obtain some information, such as parameters descriptions, that can be used for
OpenAPI Documentation. The framework also provides the possibility to control the docs
configuration directly: if simple parsing doesn't work, the user should use the @docs
decorator.

These are not meant to be a complete parsing solution, that would be worth a whole
library by itself.

See
* https://www.neoteroi.dev/blacksheep/openapi/
* http://epydoc.sourceforge.net/manual-epytext.html#the-epytext-markup-language
* tests/test_openapi_docstrings.py

"""
import re
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from textwrap import dedent
from typing import Any, Dict, List, Optional, Sequence, Type
from uuid import UUID

from .common import ParameterInfo


@dataclass
class FunctionInfo:
    summary: str
    description: str


@dataclass
class ReturnInfo:
    return_type: Any
    return_description: str


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


# TODO: should we support also arrays?
# since blacksheep supports automatic mapping of arrays from parameters, it makes
# sense to support also, for example: `str[]` or `Array<str>` / `List[str]`
TYPE_REPRS = {
    "bool": bool,
    "boolean": bool,
    "number": float,
    "integer": int,
    "int": int,
    "float": float,
    "date": date,
    "datetime": datetime,
    "uuid": UUID,
    "guid": UUID,
    "string": str,
    "str": str,
}


def type_repr_to_type(type_repr: str) -> Type:
    if type_repr in TYPE_REPRS:
        return TYPE_REPRS[type_repr]

    warnings.warn(
        f"The type representation '{type_repr}' used in docstrings is not "
        + "recognized; the parameter type will be mapped to a `str` (default). "
        + "This feature is used for automatic generation of OpenAPI Documentation. "
        + f"To improve the situation, please map '{type_repr}' to the desired type in "
        + "`blacksheep.server.openapi.docstrings.TYPE_REPRS` singleton."
    )

    return str


def collapse(value: str) -> str:
    if not value:
        return value
    return " ".join(dedent(value).split())


def handle_type_repr(parameter_info: ParameterInfo, type_repr: str) -> None:
    if not type_repr:
        return

    if " or None" in type_repr or type_repr.endswith("?"):
        parameter_info.required = False
        type_repr = type_repr.replace(" or None", "").replace("?", "")

    if ", optional" in type_repr:
        parameter_info.required = False
        type_repr = type_repr.replace(", optional", "")

    parameter_info.value_type = type_repr_to_type(type_repr)


def get_summary(description: str) -> str:
    if "\n\n" in description:
        return description.split("\n\n")[0]
    else:
        return description


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

    def get_parameters_info(self, docstring: str) -> Dict[str, ParameterInfo]:
        parameters: Dict[str, ParameterInfo] = {}
        types: Dict[str, Any] = {}

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
                description=collapse(m.group("param_desc"))
            )

        for m in self._options.param_type_rx.finditer(docstring):
            types[m.group("param_name").strip()] = m.group("type_repr").strip()

        for key, value in types.items():
            if key in parameters:
                parameter_info = parameters[key]
                handle_type_repr(parameter_info, value)

        return parameters

    def parse_docstring(self, docstring: str) -> DocstringInfo:
        return_description = None

        docstring = dedent(docstring).strip("\n")

        m = self._options.return_rx.search(docstring)
        if m:
            return_description = m.group("description")

        m = self._options.return_type_rx.search(docstring)
        if m:
            return_type = type_repr_to_type(m.group("type_repr").strip())
        else:
            return_type = None

        description_m = self._options.description_rx.match(docstring)

        if description_m:
            description = description_m.group("description").strip()
        else:
            description = ""

        return DocstringInfo(
            summary=collapse(get_summary(description)),
            description=collapse(description),
            parameters=self.get_parameters_info(docstring),
            return_type=return_type,
            return_description=collapse(return_description)
            if return_description
            else None,
        )


class IndentDocstringDialect(DocstringDialect):
    ...


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


@dataclass
class SectionFragment:
    header: str
    value: str

    def add(self, part: str) -> None:
        self.value = (self.value or "") + part


class NumpydocDialect(DocstringDialect):
    def is_match(self, docstring: str) -> bool:
        return "\nParameters" in docstring or "\nParams" in docstring

    def get_section(self, docstring: str, section_name: str) -> List[SectionFragment]:
        fragments: List[SectionFragment] = []

        section_started = False
        open_fragment: Optional[SectionFragment] = None

        for line in docstring.splitlines():
            if re.match(r"^[-\s]+$", line):
                continue

            if section_started:
                if line == "":
                    # sections are separated by \n\n
                    break

                if open_fragment is None:
                    open_fragment = SectionFragment(line, "")
                else:
                    if re.match(r"^\s+", line):
                        open_fragment.add(line)
                    else:
                        fragments.append(open_fragment)
                        open_fragment = SectionFragment(line, "")

            elif line == section_name:
                section_started = True

        if open_fragment is not None and open_fragment not in fragments:
            fragments.append(open_fragment)

        return fragments

    _sections = {"Parameters", "Params", "Returns", "Return", "Raises"}

    def get_description(self, docstring: str) -> FunctionInfo:
        lines: List[str] = []

        for line in docstring.splitlines():
            if line.strip() in self._sections:
                break
            lines.append(line)

        description = "\n".join(lines)

        return FunctionInfo(summary=get_summary(description), description=description)

    def get_return_info(self, docstring: str) -> Optional[ReturnInfo]:
        section = self.get_section(docstring, "Returns") or self.get_section(
            docstring, "Return"
        )

        if not section:
            return None

        fragment = section[0]

        return ReturnInfo(
            return_type=type_repr_to_type(fragment.header),
            return_description=collapse(fragment.value),
        )

    def get_parameters_info(self, docstring: str) -> Dict[str, ParameterInfo]:
        parameters: Dict[str, ParameterInfo] = {}

        parameters_section = self.get_section(
            docstring, "Parameters"
        ) or self.get_section(docstring, "Params")

        for fragment in parameters_section:
            if ":" not in fragment.header:
                warnings.warn(
                    f"Invalid parameter definition in docstring: {fragment.header}"
                )
                continue
            name_part, type_part = re.split(r"\s*:\s*", fragment.header)

            parameters[name_part] = ParameterInfo(
                description=collapse(fragment.value),
            )
            handle_type_repr(parameters[name_part], type_part)

        return parameters

    def parse_docstring(self, docstring: str) -> DocstringInfo:
        docstring = dedent(docstring)
        info = self.get_description(docstring)
        return_info = self.get_return_info(docstring)

        return DocstringInfo(
            summary=collapse(info.summary),
            description=collapse(info.description),
            parameters=self.get_parameters_info(docstring),
            return_type=return_info.return_type if return_info else None,
            return_description=collapse(return_info.return_description)
            if return_info
            else None,
        )


class GoogleDocDialect(DocstringDialect):
    def is_match(self, docstring: str) -> bool:
        return "\nArgs:" in docstring

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
