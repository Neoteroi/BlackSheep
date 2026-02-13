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
        # Images
        ("example.jpg", "image/jpeg"),
        ("example.jpeg", "image/jpeg"),
        ("example.png", "image/png"),
        ("example.gif", "image/gif"),
        ("example.bmp", "image/bmp"),
        ("example.svg", "image/svg+xml"),
        ("example.ico", "image/vnd.microsoft.icon"),
        ("example.tiff", "image/tiff"),
        ("example.tif", "image/tiff"),
        # Audio
        ("example.mp3", "audio/mpeg"),
        ("example.wav", "audio/x-wav"),
        ("example.ogg", "audio/ogg"),
        ("example.aac", "audio/aac"),
        # Video
        ("example.mp4", "video/mp4"),
        ("example.avi", "video/x-msvideo"),
        ("example.mov", "video/quicktime"),
        ("example.mpeg", "video/mpeg"),
        ("example.mpg", "video/mpeg"),
        ("example.webm", "video/webm"),
        # Documents
        ("document.pdf", "application/pdf"),
        ("document.doc", "application/msword"),
        ("spreadsheet.xls", "application/vnd.ms-excel"),
        ("presentation.ppt", "application/vnd.ms-powerpoint"),
        # Text
        ("hello.txt", "text/plain"),
        ("example.csv", "text/csv"),
        ("example.html", "text/html"),
        ("example.htm", "text/html"),
        ("example.css", "text/css"),
        ("example.xml", "text/xml"),
        # Programming languages
        (
            "example.js",
            (
                "text/javascript"
                if sys.version_info >= (3, 12)
                else "application/javascript"
            ),
        ),
        ("example.json", "application/json"),
        ("example.py", "text/x-python"),
        ("example.c", "text/plain"),
        # Archives
        ("archive.zip", "application/zip"),
        ("archive.tar", "application/x-tar"),
        # Fonts
        ("example.woff2", "font/woff2"),
        # Special cases and unsupported extensions (return application/octet-stream)
        (".gitignore", "application/octet-stream"),
        ("ØØ Void.album", "application/octet-stream"),
        ("", "application/octet-stream"),
    ],
)
def test_get_mime_type(full_path, expected_result):
    assert get_mime_type_from_name(full_path) == expected_result
