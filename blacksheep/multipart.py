from typing import Dict, Generator, Iterable, Optional, Tuple

from blacksheep.contents import FormPart


def get_boundary_from_header(value: bytes) -> bytes:
    return value.split(b"=", 1)[1].split(b" ", 1)[0]


def _remove_last_crlf(value: bytes) -> bytes:
    if value.endswith(b"\r\n"):
        return value[:-2]
    if value.endswith(b"\n"):
        return value[:-1]
    return value


def split_multipart(value: bytes) -> Iterable[bytes]:
    """
    Splits a whole multipart/form-data payload into single parts
    without boundary.
    """
    value = value.strip(b" ")
    boundary = value[: value.index(b"\n")].rstrip(b"\r")

    for part in value.split(boundary):
        part = _remove_last_crlf(part.lstrip(b"\r\n"))
        if part == b"" or part == b"--":
            continue
        yield part


def split_headers(value: bytes) -> Iterable[Tuple[bytes, bytes]]:
    """
    Splits a whole portion of multipart form data representing headers
    into name, value pairs.
    """
    #
    # Examples of whole portions:
    #
    # Content-Disposition: form-data; name="two"
    # Content-Disposition: form-data; name="file_example";
    #   filename="example-001.png"\r\nContent-Type: image/png
    #
    for raw_header in value.split(b"\r\n"):
        header_name, header_value = raw_header.split(b":", 1)
        yield header_name.lower(), header_value.lstrip(b" ")


def split_content_disposition_values(
    value: bytes,
) -> Iterable[Tuple[bytes, Optional[bytes]]]:
    """
    Parses a single header into key, value pairs.
    """
    for part in value.split(b";"):
        if b"=" in part:
            name, value = part.split(b"=", 1)
            yield name.lower().strip(b" "), value.strip(b'" ')
        else:
            yield b"type", part


def parse_content_disposition_values(value: bytes) -> Dict[bytes, Optional[bytes]]:
    return dict(split_content_disposition_values(value))


class CharsetPart(Exception):
    def __init__(self, default_charset: bytes):
        self.default_charset = default_charset


def parse_part(value: bytes, default_charset: Optional[bytes]) -> FormPart:
    """Parses a single multipart/form-data part."""
    raw_headers, data = value.split(b"\r\n\r\n", 1)

    headers = dict(split_headers(raw_headers))

    content_disposition = headers.get(b"content-disposition")

    if not content_disposition:
        raise ValueError(
            "Missing Content-Disposition header in multipart/form-data part."
        )

    content_disposition_values = parse_content_disposition_values(content_disposition)

    field_name = content_disposition_values.get(b"name")

    if field_name == b"_charset_":
        # NB: handling charset...
        # https://tools.ietf.org/html/rfc7578#section-4.6
        raise CharsetPart(data)

    content_type = headers.get(b"content-type", None)

    return FormPart(
        field_name or b"",
        data,
        content_type,
        content_disposition_values.get(b"filename"),
        default_charset,
    )


def parse_multipart(value: bytes) -> Generator[FormPart, None, None]:
    default_charset = None

    for part_bytes in split_multipart(value):
        try:
            yield parse_part(part_bytes, default_charset)
        except CharsetPart as charset:
            default_charset = charset.default_charset
