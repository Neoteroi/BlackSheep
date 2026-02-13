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
        ("no_extension", "application/octet-stream"),
        ("example.webp", "image/webp"),
        ("example.flac", "application/octet-stream"),  # Not in standard mimetypes
        ("example.m4a", "application/octet-stream"),  # Not in standard mimetypes
        ("example.mkv", "application/octet-stream"),  # Not in standard mimetypes
        ("example.flv", "application/octet-stream"),  # Not in standard mimetypes
        ("example.wmv", "application/octet-stream"),  # Not in standard mimetypes
        ("document.docx", "application/octet-stream"),  # Not in standard mimetypes
        ("spreadsheet.xlsx", "application/octet-stream"),  # Not in standard mimetypes
        ("presentation.pptx", "application/octet-stream"),  # Not in standard mimetypes
        ("document.odt", "application/octet-stream"),  # Not in standard mimetypes
        ("spreadsheet.ods", "application/octet-stream"),  # Not in standard mimetypes
        ("presentation.odp", "application/octet-stream"),  # Not in standard mimetypes
        ("document.rtf", "text/rtf"),
        ("example.md", "text/markdown"),
        ("example.java", "application/octet-stream"),  # Not in standard mimetypes
        ("example.cpp", "application/octet-stream"),  # Not in standard mimetypes
        ("example.rs", "application/octet-stream"),  # Not in standard mimetypes
        ("example.go", "application/octet-stream"),  # Not in standard mimetypes
        ("example.ts", "application/octet-stream"),  # Not in standard mimetypes
        ("archive.gz", "application/octet-stream"),  # Not in standard mimetypes
        ("archive.bz2", "application/octet-stream"),  # Not in standard mimetypes
        ("archive.7z", "application/octet-stream"),  # Not in standard mimetypes
        ("archive.rar", "application/octet-stream"),  # Not in standard mimetypes
        ("example.woff", "application/octet-stream"),  # Not in standard mimetypes
        ("example.ttf", "application/octet-stream"),  # Not in standard mimetypes
        ("example.otf", "application/octet-stream"),  # Not in standard mimetypes
        # Case insensitive
        ("UPPERCASE.PDF", "application/pdf"),
        ("MixedCase.JpEg", "image/jpeg"),
        ("UpperCase.MP3", "audio/mpeg"),
        ("MixedCase.MP4", "video/mp4"),
    ],
)
def test_get_mime_type(full_path, expected_result):
    assert get_mime_type_from_name(full_path) == expected_result
