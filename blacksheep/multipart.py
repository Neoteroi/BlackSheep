from typing import AsyncIterable, Generator, Iterable

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


def split_headers(value: bytes) -> Iterable[tuple[bytes, bytes]]:
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
) -> Iterable[tuple[bytes, bytes]] | None:
    """
    Parses a single header into key, value pairs.
    """
    for part in value.split(b";"):
        if b"=" in part:
            name, value = part.split(b"=", 1)
            yield name.lower().strip(b" "), value.strip(b'" ')
        else:
            yield b"type", part


def parse_content_disposition_values(value: bytes) -> dict[bytes, bytes | None]:
    return dict(split_content_disposition_values(value))


class CharsetPart(Exception):
    def __init__(self, default_charset: bytes):
        self.default_charset = default_charset


def parse_part(value: bytes, default_charset: bytes | None) -> FormPart:
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

    # TODO: convert bytes to str? If we keep bytes, it's most performant because we
    # avoid the .decode call on fields that we don't even know if the user wants to read
    # However, keeping bytes feels cumbersome when the developer wants to read fields
    # like content_type, file_name when given, etc.
    return FormPart(
        field_name or b"",
        data,
        content_type,
        content_disposition_values.get(b"filename"),
        default_charset,
    )


def parse_multipart(value: bytes) -> Generator[FormPart, None, None]:
    """
    Parses multipart/form-data from a complete byte string.

    Warning: This method loads the entire request body into memory. For large file
    uploads (e.g., images, videos, documents > 10MB), consider using streaming
    alternatives:

    - `parse_multipart_async()` for async streaming parsing
    - `request.stream_multipart()` for high-level streaming API

    These alternatives process multipart data chunk-by-chunk without loading
    the entire payload into memory, preventing memory pressure and improving
    scalability for file upload endpoints.

    Args:
        value: The complete multipart/form-data body as bytes

    Yields:
        FormPart objects parsed from the multipart body

    Example:
        ```python
        # For small uploads (<10MB)
        parts = list(parse_multipart(request_body))

        # For large uploads, use streaming instead:
        async for part in parse_multipart_async(stream, boundary):
            await process_part(part)
        ```
    """
    default_charset = None

    for part_bytes in split_multipart(value):
        try:
            yield parse_part(part_bytes, default_charset)
        except CharsetPart as charset:
            default_charset = charset.default_charset


async def parse_multipart_async(
    stream: AsyncIterable[bytes], boundary: bytes
) -> AsyncIterable[FormPart]:
    """
    Parses multipart/form-data from an async stream, yielding FormPart objects
    as they become available.

    This allows processing large files without loading the entire request body
    into memory.

    Args:
        stream: Async iterable of byte chunks from the request body
        boundary: The boundary bytes from the Content-Type header

    Yields:
        FormPart objects as they are parsed from the stream
    """
    boundary_delimiter = b"--" + boundary
    end_boundary = boundary_delimiter + b"--"

    buffer = bytearray()
    default_charset = None
    in_part = False
    part_buffer = bytearray()

    async for chunk in stream:
        buffer.extend(chunk)

        while True:
            if not in_part:
                # Look for boundary to start a new part
                boundary_index = buffer.find(boundary_delimiter)
                if boundary_index == -1:
                    # Keep last len(boundary_delimiter) bytes in case boundary is split
                    if len(buffer) > len(boundary_delimiter):
                        buffer = buffer[-len(boundary_delimiter):]
                    break

                # Check if this is the end boundary
                if buffer[boundary_index:].startswith(end_boundary):
                    return

                # Skip to after boundary and CRLF
                after_boundary = boundary_index + len(boundary_delimiter)
                if after_boundary < len(buffer):
                    if buffer[after_boundary:after_boundary+2] == b"\r\n":
                        after_boundary += 2
                    elif buffer[after_boundary:after_boundary+1] == b"\n":
                        after_boundary += 1

                buffer = buffer[after_boundary:]
                in_part = True
                part_buffer.clear()

            else:
                # Look for the next boundary to end current part
                next_boundary = buffer.find(boundary_delimiter)

                if next_boundary == -1:
                    # No boundary found, keep accumulating but leave space for boundary check
                    if len(buffer) > len(boundary_delimiter) + 4:  # +4 for \r\n before boundary
                        safe_amount = len(buffer) - len(boundary_delimiter) - 4
                        part_buffer.extend(buffer[:safe_amount])
                        buffer = buffer[safe_amount:]
                    break

                # Found boundary, complete the part
                part_data = bytes(part_buffer) + bytes(buffer[:next_boundary])

                # Remove trailing CRLF before boundary
                part_data = _remove_last_crlf(part_data)

                # Parse and yield the part
                if part_data:
                    try:
                        form_part = parse_part(part_data, default_charset)
                        yield form_part
                    except CharsetPart as charset:
                        default_charset = charset.default_charset

                # Move past the boundary we just found
                buffer = buffer[next_boundary:]
                in_part = False
                part_buffer.clear()
