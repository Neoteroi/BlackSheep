from mimetypes import MimeTypes

mime = MimeTypes()


DEFAULT_MIME = "application/octet-stream"

MIME_BY_EXTENSION = {
    ".ogg": "audio/ogg",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".woff2": "font/woff2",
}


def get_file_extension_from_name(name: str) -> str:
    if not name:
        return ""
    return name[name.rfind(".") :].lower()


def get_mime_type_from_name(file_name: str) -> str:
    extension = get_file_extension_from_name(file_name)
    mime_type = mime.guess_type(file_name)[0] or DEFAULT_MIME

    if mime_type == DEFAULT_MIME:
        mime_type = MIME_BY_EXTENSION.get(extension, DEFAULT_MIME)
    return mime_type
