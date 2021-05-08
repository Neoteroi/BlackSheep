import pytest
from blacksheep.server.openapi.common import ParameterInfo
from blacksheep.server.openapi.docstrings import EpytextDialect, ReStructuredTextDialect
from blacksheep.server.openapi.docstrings import DocstringInfo, _collapse


@pytest.mark.parametrize(
    "docstring,expected_info",
    [
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
                summary=_collapse(
                    """
                    This is a paragraph. Paragraphs can
                    span multiple lines, and can contain
                    I{inline markup}.
                    """
                ),
                description=_collapse(
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
        ),
    ],
)
def test_epytext_dialect(docstring, expected_info):
    dialect = EpytextDialect()

    info = dialect.parse_docstring(docstring)
    assert expected_info == info


@pytest.mark.parametrize(
    "docstring,expected_info",
    [
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

    info = dialect.parse_docstring(docstring)
    assert expected_info == info
