import pytest

from blacksheep.multipart import (
    _remove_last_crlf
)


@pytest.mark.parametrize(
    "input,output",
    [
        (b"example", b"example"),
        (b"example\r\n", b"example"),
        (b"example\n", b"example"),
        (b"example\r\n\r\n", b"example\r\n"),
        (b"example\n\n", b"example\n"),
    ],
)
def test_remove_last_crlf(input, output):
    assert _remove_last_crlf(input) == output
