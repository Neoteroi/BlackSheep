import ntpath
import pathlib
from mimetypes import MimeTypes
from typing import Tuple

mime = MimeTypes()


DEFAULT_MIME = 'application/octet-stream'

MIME_BY_EXTENSION = {
    '.ogg': 'audio/ogg',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.woff2': 'font/woff2'
}


def get_file_extension_from_name(name: str) -> str:
    if not name:
        return ''

    extension = pathlib.Path(name).suffix
    return extension.lower()


def get_file_name_from_path(full_path: str) -> str:
    head, tail = ntpath.split(full_path)
    return tail or ntpath.basename(head)


def get_mime_type(file_name: str) -> str:
    extension = get_file_extension_from_name(file_name)
    mime_type = mime.guess_type(file_name)[0] or DEFAULT_MIME

    if mime_type == DEFAULT_MIME and extension in MIME_BY_EXTENSION:
        mime_type = MIME_BY_EXTENSION.get(extension, DEFAULT_MIME)

    return mime_type


def get_best_mime_type(file_name: str) -> Tuple[str, str]:
    extension = get_file_extension_from_name(file_name)
    mime_type = mime.guess_type(file_name)[0] or DEFAULT_MIME

    if mime_type == DEFAULT_MIME and extension in MIME_BY_EXTENSION:
        mime_type = MIME_BY_EXTENSION.get(extension, DEFAULT_MIME)

    return extension, mime_type
