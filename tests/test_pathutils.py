import sys

import pytest

from blacksheep.common.files.pathsutils import (
    get_file_extension_from_name,
    get_mime_type_from_name,
)


@pytest.mark.parametrize(
    "full_path,expected_result",
    [
        ("hello.txt", ".txt"),
        (".gitignore", ".gitignore"),
        ("ØØ Void.album", ".album"),
        ("", ""),
    ],
)
def test_get_file_extension_from_name(full_path, expected_result):
    assert get_file_extension_from_name(full_path) == expected_result


@pytest.mark.parametrize(
    "full_path,expected_result",
    [
        ("example.ogg", "audio/ogg"),
        ("example.jpg", "image/jpeg"),
        ("example.jpeg", "image/jpeg"),
        ("example.png", "image/png"),
        (
            "example.js",
            (
                "text/javascript"
                if sys.version_info >= (3, 12)
                else "application/javascript"
            ),
        ),
        ("example.json", "application/json"),
        ("example.woff2", "font/woff2"),
        ("hello.txt", "text/plain"),
        (".gitignore", "application/octet-stream"),
        ("ØØ Void.album", "application/octet-stream"),
        ("", "application/octet-stream"),
    ],
)
def test_get_mime_type(full_path, expected_result):
    assert get_mime_type_from_name(full_path) == expected_result
