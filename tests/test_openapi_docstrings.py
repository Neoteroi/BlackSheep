from typing import List

import pytest

from blacksheep.server.openapi.common import ParameterInfo
from blacksheep.server.openapi.docstrings import (
    DocstringInfo,
    EpytextDialect,
    GoogleDocDialect,
    NumpydocDialect,
    ReStructuredTextDialect,
    collapse,
)


@pytest.mark.parametrize(
    "docstring,expected_info,match",
    [
        (
            """
            Example with lists of values.

            @param List[str] a: list of str
            @param int[] b: list of int
            @param str[] c: list of str
            """,
            DocstringInfo(
                summary="Example with lists of values.",
                description="Example with lists of values.",
                parameters={
                    "a": ParameterInfo("list of str", value_type=List[str]),
                    "b": ParameterInfo("list of int", value_type=List[int]),
                    "c": ParameterInfo("list of str", value_type=List[str]),
                },
            ),
            True,
        ),
        (
            """
            Example with lists of values.

            @param a: list of str
            @param b: list of int
            @param c: list of str
            @type a: List[str]
            @type b: int[]
            @type c: str[]
            """,
            DocstringInfo(
                summary="Example with lists of values.",
                description="Example with lists of values.",
                parameters={
                    "a": ParameterInfo("list of str", value_type=List[str]),
                    "b": ParameterInfo("list of int", value_type=List[int]),
                    "c": ParameterInfo("list of str", value_type=List[str]),
                },
            ),
            True,
        ),
        (
            """
            Return the x intercept of the line M{y=m*x+b}. The X{x intercept}
            of a line is the point at which it crosses the x axis (M{y=0}).

            This function can be used in conjuction with L{z_transform} to
            find an arbitrary function's zeros.

            @param number m: The slope of the line.
            @param number b: The y intercept of the line.  The X{y intercept} of a
                    line is the point at which it crosses the y axis (M{x=0}).
            @rtype:   number
            @return:  the x intercept of the line M{y=m*x+b}.
            """,
            DocstringInfo(
                summary="Return the x intercept of the line M{y=m*x+b}. "
                + "The X{x intercept} of a line is the point at which it "
                + "crosses the x axis (M{y=0}).",
                description="Return the x intercept of the line M{y=m*x+b}. "
                + "The X{x intercept} of a line is the point at which it "
                + "crosses the x axis (M{y=0}). This function can be used in "
                + "conjuction with L{z_transform} to find an arbitrary function's zeros.",
                parameters={
                    "m": ParameterInfo("The slope of the line.", value_type=float),
                    "b": ParameterInfo(
                        "The y intercept of the line. The X{y intercept} "
                        + "of a line is the point at which it crosses the y axis (M{x=0}).",
                        value_type=float,
                    ),
                },
                return_type=float,
                return_description="the x intercept of the line M{y=m*x+b}.",
            ),
            True,
        ),
        (
            """
            Return the x intercept of the line M{y=m*x+b}. The X{x intercept}
            of a line is the point at which it crosses the x axis (M{y=0}).

            This function can be used in conjuction with L{z_transform} to
            find an arbitrary function's zeros.

            @type  m: number
            @param m: The slope of the line.
            @type  b: number
            @param b: The y intercept of the line.  The X{y intercept} of a
                    line is the point at which it crosses the y axis (M{x=0}).
            @rtype:   number
            @return:  the x intercept of the line M{y=m*x+b}.
            """,
            DocstringInfo(
                summary="Return the x intercept of the line M{y=m*x+b}. "
                + "The X{x intercept} of a line is the point at which it "
                + "crosses the x axis (M{y=0}).",
                description="Return the x intercept of the line M{y=m*x+b}. "
                + "The X{x intercept} of a line is the point at which it "
                + "crosses the x axis (M{y=0}). This function can be used in "
                + "conjuction with L{z_transform} to find an arbitrary function's zeros.",
                parameters={
                    "m": ParameterInfo("The slope of the line.", value_type=float),
                    "b": ParameterInfo(
                        "The y intercept of the line. The X{y intercept} "
                        + "of a line is the point at which it crosses the y axis (M{x=0}).",
                        value_type=float,
                    ),
                },
                return_type=float,
                return_description="the x intercept of the line M{y=m*x+b}.",
            ),
            True,
        ),
        (
            """
            Lorem ipsum dolor sit amet.

            @type  value: int
            @param value: Some value.
            """,
            DocstringInfo(
                summary="Lorem ipsum dolor sit amet.",
                description="Lorem ipsum dolor sit amet.",
                parameters={
                    "value": ParameterInfo("Some value.", value_type=int),
                },
                return_type=None,
                return_description=None,
            ),
            True,
        ),
        (
            """
            Lorem ipsum dolor sit amet.

            @type  value: int or None
            @param value: Some value.
            """,
            DocstringInfo(
                summary="Lorem ipsum dolor sit amet.",
                description="Lorem ipsum dolor sit amet.",
                parameters={
                    "value": ParameterInfo(
                        "Some value.", value_type=int, required=False
                    ),
                },
                return_type=None,
                return_description=None,
            ),
            True,
        ),
        (
            """
            Lorem ipsum dolor sit amet.

            @type  value: int?
            @param value: Some value.
            """,
            DocstringInfo(
                summary="Lorem ipsum dolor sit amet.",
                description="Lorem ipsum dolor sit amet.",
                parameters={
                    "value": ParameterInfo(
                        "Some value.", value_type=int, required=False
                    ),
                },
                return_type=None,
                return_description=None,
            ),
            True,
        ),
        (
            """
            This is a javadoc style.

            @param param1: this is a first param
            @param param2: this is a second param
            @return: this is a description of what is returned
            @raise keyError: raises an exception
            """,
            DocstringInfo(
                summary="This is a javadoc style.",
                description="This is a javadoc style.",
                parameters={
                    "param1": ParameterInfo("this is a first param"),
                    "param2": ParameterInfo("this is a second param"),
                },
                return_description="this is a description of what is returned",
            ),
            True,
        ),
        (
            """
            This is a paragraph. Paragraphs can
            span multiple lines, and can contain
            I{inline markup}.

            This is another paragraph.  Paragraphs
            are separated by blank lines.
            """,
            DocstringInfo(
                summary=collapse(
                    """
                    This is a paragraph. Paragraphs can
                    span multiple lines, and can contain
                    I{inline markup}.
                    """
                ),
                description=collapse(
                    """
                    This is a paragraph. Paragraphs can
                    span multiple lines, and can contain
                    I{inline markup}.

                    This is another paragraph.  Paragraphs
                    are separated by blank lines.
                    """
                ),
                parameters={},
            ),
            False,
        ),
    ],
)
def test_epytext_dialect(docstring, expected_info, match):
    dialect = EpytextDialect()
    assert dialect.is_match(docstring) is match

    info = dialect.parse_docstring(docstring)
    assert expected_info == info


@pytest.mark.parametrize(
    "docstring,expected_info",
    [
        (
            """
            Example with lists of values.

            :param List[str] a: list of str
            :param int[] b: list of int
            :param str[] c: list of str
            """,
            DocstringInfo(
                summary="Example with lists of values.",
                description="Example with lists of values.",
                parameters={
                    "a": ParameterInfo("list of str", value_type=List[str]),
                    "b": ParameterInfo("list of int", value_type=List[int]),
                    "c": ParameterInfo("list of str", value_type=List[str]),
                },
            ),
        ),
        (
            """
            Example with unrecognized type.

            :param foo a: some unrecognized type
            """,
            DocstringInfo(
                summary="Example with unrecognized type.",
                description="Example with unrecognized type.",
                parameters={
                    "a": ParameterInfo("some unrecognized type (foo)", value_type=None),
                },
            ),
        ),
        (
            """
            Example with lists of values.

            :param a: list of str
            :param b: list of int
            :param c: list of str
            :type a: List[str]
            :type b: int[]
            :type c: str[]
            """,
            DocstringInfo(
                summary="Example with lists of values.",
                description="Example with lists of values.",
                parameters={
                    "a": ParameterInfo("list of str", value_type=List[str]),
                    "b": ParameterInfo("list of int", value_type=List[int]),
                    "c": ParameterInfo("list of str", value_type=List[str]),
                },
            ),
        ),
        (
            """
            Send a message to a recipient

            :param sender: The person sending the message
            :param recipient: The recipient of the message
            :param message_body: The body of the message
            :param priority: The priority of the message, can be a number 1-5
            :type priority: integer or None
            :return: the message id
            :rtype: int
            :raises ValueError: if the message_body exceeds 160 characters
            :raises TypeError: if the message_body is not a basestring
            """,
            DocstringInfo(
                summary="Send a message to a recipient",
                description="Send a message to a recipient",
                parameters={
                    "sender": ParameterInfo(
                        "The person sending the message", value_type=None
                    ),
                    "recipient": ParameterInfo(
                        "The recipient of the message", value_type=None
                    ),
                    "message_body": ParameterInfo(
                        "The body of the message", value_type=None
                    ),
                    "priority": ParameterInfo(
                        "The priority of the message, can be a number 1-5",
                        value_type=int,
                        required=False,
                    ),
                },
                return_type=int,
                return_description="the message id",
            ),
        ),
        (
            """
            Send a message to a recipient

            :param str sender: The person sending the message
            :param str recipient: The recipient of the message
            :param str message_body: The body of the message
            :param integer or None priority: The priority of the message, can be a number 1-5
            :return: the message id
            :rtype: int
            :raises ValueError: if the message_body exceeds 160 characters
            :raises TypeError: if the message_body is not a basestring
            """,
            DocstringInfo(
                summary="Send a message to a recipient",
                description="Send a message to a recipient",
                parameters={
                    "sender": ParameterInfo(
                        "The person sending the message", value_type=str
                    ),
                    "recipient": ParameterInfo(
                        "The recipient of the message", value_type=str
                    ),
                    "message_body": ParameterInfo(
                        "The body of the message", value_type=str
                    ),
                    "priority": ParameterInfo(
                        "The priority of the message, can be a number 1-5",
                        value_type=int,
                        required=False,
                    ),
                },
                return_type=int,
                return_description="the message id",
            ),
        ),
    ],
)
def test_rest_dialect(docstring, expected_info):
    dialect = ReStructuredTextDialect()
    assert dialect.is_match(docstring)

    info = dialect.parse_docstring(docstring)
    assert expected_info == info


@pytest.mark.parametrize(
    "docstring,expected_info,match",
    [
        (
            """
            My numpydoc description of a kind
            of very exhautive numpydoc format docstring.

            Parameters
            ----------
            first : str
                the 1st param name `first`
            second :
                the 2nd param
            third : int, optional
                the 3rd param, by default 'value'

            Returns
            -------
            string
                a value in a string

            Raises
            ------
            KeyError
                when a key error
            OtherError
                when an other error
            """,
            DocstringInfo(
                summary="My numpydoc description of a kind of very exhautive "
                + "numpydoc format docstring.",
                description="My numpydoc description of a kind of very exhautive "
                + "numpydoc format docstring.",
                parameters={
                    "first": ParameterInfo(
                        "the 1st param name `first`", value_type=str
                    ),
                    "second": ParameterInfo("the 2nd param", value_type=None),
                    "third": ParameterInfo(
                        "the 3rd param, by default 'value'",
                        value_type=int,
                        required=False,
                    ),
                },
                return_type=str,
                return_description="a value in a string",
            ),
            True,
        ),
        (
            """
            Example with lists of values.

            Parameters
            ----------
            a : List[str]
                list of str
            b : int[]
                list of int
            c : str[]
                list of str
            """,
            DocstringInfo(
                summary="Example with lists of values.",
                description="Example with lists of values.",
                parameters={
                    "a": ParameterInfo("list of str", value_type=List[str]),
                    "b": ParameterInfo("list of int", value_type=List[int]),
                    "c": ParameterInfo("list of str", value_type=List[str]),
                },
            ),
            True,
        ),
        (
            """
            Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod
            tempor incididunt ut labore et dolore magna aliqua.

            Ut enim ad minim  veniam, quis nostrud exercitation ullamco laboris nisi ut
            aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in
            voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint
            occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit
            anim id est laborum.

            Parameters
            ----------
            lorem : str
                A very long description spanning across multiple lines;
                Ut enim ad minim  veniam, quis nostrud exercitation ullamco laboris nisi
                ut aliquip ex ea commodo consequat. Duis aute irure dolor in
                reprehenderit.
            """,
            DocstringInfo(
                summary="Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed "
                + "do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
                description="Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed "
                + "do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
                + "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris "
                + "nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in "
                + "reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
                + "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in "
                + "culpa qui officia deserunt mollit anim id est laborum.",
                parameters={
                    "lorem": ParameterInfo(
                        collapse(
                            """
                            A very long description spanning across multiple lines;
                            Ut enim ad minim veniam, quis nostrud exercitation ullamco
                            laboris nisi ut aliquip ex ea commodo consequat. Duis aute
                            irure dolor in reprehenderit."""
                        ),
                        value_type=str,
                    ),
                },
                return_type=None,
                return_description=None,
            ),
            True,
        ),
        (
            """
            My numpydoc description of a kind
            of very exhautive numpydoc format docstring.

            Params
            ----------
            first : str
                the 1st param name `first`
            second :
                the 2nd param
            third : int, optional
                the 3rd param, by default 'value'

            Returns
            -------
            string
                a value in a string

            Raises
            ------
            KeyError
                when a key error
            OtherError
                when an other error
            """,
            DocstringInfo(
                summary="My numpydoc description of a kind of very exhautive "
                + "numpydoc format docstring.",
                description="My numpydoc description of a kind of very exhautive "
                + "numpydoc format docstring.",
                parameters={
                    "first": ParameterInfo(
                        "the 1st param name `first`", value_type=str
                    ),
                    "second": ParameterInfo("the 2nd param", value_type=None),
                    "third": ParameterInfo(
                        "the 3rd param, by default 'value'",
                        value_type=int,
                        required=False,
                    ),
                },
                return_type=str,
                return_description="a value in a string",
            ),
            True,
        ),
        (
            """
            Lorem ipsum dolor sit amet 2.

            Parameters
            ----------
            filename : str
            copy : bool
            dtype : data-type
            iterable : iterable object
            shape : int or tuple of int
            files : list of str

            Returns
            -------
            string
                a value in a string

            Raises
            ------
            KeyError
                when a key error
            OtherError
                when an other error
            """,
            DocstringInfo(
                summary="Lorem ipsum dolor sit amet 2.",
                description="Lorem ipsum dolor sit amet 2.",
                parameters={
                    "filename": ParameterInfo("", value_type=str),
                    "copy": ParameterInfo("", value_type=bool),
                    "dtype": ParameterInfo("data-type", value_type=None),
                    "iterable": ParameterInfo("iterable object", value_type=None),
                    "shape": ParameterInfo("int or tuple of int", value_type=None),
                    "files": ParameterInfo("list of str", value_type=None),
                },
                return_type=str,
                return_description="a value in a string",
            ),
            True,
        ),
        (
            """
            Lorem ipsum dolor sit amet.

            Custom
            ----------
            Hello World!
            """,
            DocstringInfo(
                summary="Lorem ipsum dolor sit amet.",
                description="Lorem ipsum dolor sit amet.",
                parameters={},
            ),
            False,
        ),
    ],
)
def test_numpydoc_dialect(docstring, expected_info, match):
    dialect = NumpydocDialect()
    assert dialect.is_match(docstring) is match

    info = dialect.parse_docstring(docstring)
    assert expected_info == info


def test_numpydoc_dialect_warns_about_invalid_parameter():
    docstring = """
    Lorem ipsum dolor sit amet.

    Parameters
    ----------
    something_invalid
    """

    with pytest.warns(
        UserWarning,
        match="Invalid parameter definition in docstring: something_invalid",
    ):
        dialect = NumpydocDialect()
        info = dialect.parse_docstring(docstring)
        assert info is not None


def test_googledoc_dialect_warns_about_invalid_parameter():
    docstring = """
    Lorem ipsum dolor sit amet.

    Args:
        something_invalid
    """

    with pytest.warns(
        UserWarning,
        match="Invalid parameter definition in docstring: something_invalid",
    ):
        dialect = GoogleDocDialect()
        info = dialect.parse_docstring(docstring)
        assert info is not None


@pytest.mark.parametrize(
    "docstring,expected_info",
    [
        (
            """
            This is an example of Google style.

            Args:
                param1: This is the first param.
                param2: This is a second param.

            Returns:
                This is a description of what is returned.

            Raises:
                KeyError: Raises an exception.
            """,
            DocstringInfo(
                summary="This is an example of Google style.",
                description="This is an example of Google style.",
                parameters={
                    "param1": ParameterInfo("This is the first param."),
                    "param2": ParameterInfo("This is a second param."),
                },
                return_type=None,
                return_description="This is a description of what is returned.",
            ),
        ),
        (
            """
            This is an example of Google style.

            Args:
                param1: This is the first param.
                param2: This is a second param.

            Raises:
                KeyError: Raises an exception.
            """,
            DocstringInfo(
                summary="This is an example of Google style.",
                description="This is an example of Google style.",
                parameters={
                    "param1": ParameterInfo("This is the first param."),
                    "param2": ParameterInfo("This is a second param."),
                },
                return_type=None,
                return_description=None,
            ),
        ),
        (
            """
            This is an example of Google style.

            Args:
                param1: This is the first param.
                param2: This is a second param.
            """,
            DocstringInfo(
                summary="This is an example of Google style.",
                description="This is an example of Google style.",
                parameters={
                    "param1": ParameterInfo("This is the first param."),
                    "param2": ParameterInfo("This is a second param."),
                },
                return_type=None,
                return_description=None,
            ),
        ),
        (
            """
            Fetches rows from a Smalltable.

            Retrieves rows pertaining to the given keys from the Table instance
            represented by table_handle. String keys will be UTF-8 encoded.

            Args:
                table_handle:
                    An open smalltable.Table instance.
                keys:
                    A sequence of strings representing the key of each table row to
                    fetch. String keys will be UTF-8 encoded.
                require_all_keys:
                    Optional; If require_all_keys is True only rows with values set
                    for all keys will be returned.

            Returns:
                A dict mapping keys to the corresponding table row data
                fetched. Each row is represented as a tuple of strings. For
                example:

                {b'Serak': ('Rigel VII', 'Preparer'),
                b'Zim': ('Irk', 'Invader'),
                b'Lrrr': ('Omicron Persei 8', 'Emperor')}

                Returned keys are always bytes. If a key from the keys argument is
                missing from the dictionary, then that row was not found in the
                table (and require_all_keys must have been False).

            Raises:
                IOError: An error occurred accessing the smalltable.
            """,
            DocstringInfo(
                summary="Fetches rows from a Smalltable.",
                description="Fetches rows from a Smalltable. Retrieves rows "
                + "pertaining to the given keys from the Table instance represented "
                + "by table_handle. String keys will be UTF-8 encoded.",
                parameters={
                    "table_handle": ParameterInfo("An open smalltable.Table instance."),
                    "keys": ParameterInfo(
                        "A sequence of strings representing the key of each table "
                        "row to fetch. String keys will be UTF-8 encoded."
                    ),
                    "require_all_keys": ParameterInfo(
                        "Optional; If require_all_keys is True only rows with values set for "
                        "all keys will be returned.",
                    ),
                },
                return_type=None,
                return_description=collapse(
                    """
                    A dict mapping keys to the corresponding table row data
                    fetched. Each row is represented as a tuple of strings. For
                    example:

                    {b'Serak': ('Rigel VII', 'Preparer'),
                    b'Zim': ('Irk', 'Invader'),
                    b'Lrrr': ('Omicron Persei 8', 'Emperor')}

                    Returned keys are always bytes. If a key from the keys argument is
                    missing from the dictionary, then that row was not found in the
                    table (and require_all_keys must have been False).
                    """
                ),
            ),
        ),
    ],
)
def test_googledoc_dialect(docstring, expected_info):
    dialect = GoogleDocDialect()
    assert dialect.is_match(docstring)

    info = dialect.parse_docstring(docstring)
    assert expected_info == info
