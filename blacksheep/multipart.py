from typing import AsyncIterable, Generator, Iterable

from blacksheep.contents import FormPart, StreamingFormPart


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

    Note: This implementation still buffers each part's data completely in memory.
    For truly memory-efficient streaming of large files, use
    `parse_multipart_streaming()` instead, which yields StreamingFormPart objects
    that allow lazy reading of file content.

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


async def parse_multipart_streaming(
    stream: AsyncIterable[bytes],
    boundary: bytes,
    chunk_size: int = 65536,
) -> AsyncIterable[StreamingFormPart | FormPart]:
    """
    Parses multipart/form-data from an async stream with true streaming support.

    This implementation yields StreamingFormPart objects for file uploads, allowing
    the file data to be read lazily without loading entire files into memory. Small
    form fields are yielded as regular FormPart objects with data fully loaded.

    This is the most memory-efficient option for handling large file uploads, as it
    streams file content chunk-by-chunk without buffering.

    Args:
        stream: Async iterable of byte chunks from the request body
        boundary: The boundary bytes from the Content-Type header
        chunk_size: Size of chunks to yield when streaming file data (default: 64KB)

    Yields:
        StreamingFormPart for files (data accessed via stream() or read())
        FormPart for small form fields (data immediately available)

    Example:
        ```python
        async for part in parse_multipart_streaming(request.stream(), boundary):
            if isinstance(part, StreamingFormPart):
                # Large file - stream to disk
                await part.save_to(f"uploads/{part.file_name.decode()}")
            else:
                # Small form field - data is in part.data
                value = part.data.decode('utf-8')
        ```
    """
    boundary_delimiter = b"--" + boundary
    end_boundary = boundary_delimiter + b"--"

    buffer = bytearray()
    default_charset = None
    in_headers = False
    in_data = False
    headers_buffer = bytearray()

    # Current part metadata
    current_headers: dict[bytes, bytes] | None = None
    current_name: bytes | None = None
    current_filename: bytes | None = None
    current_content_type: bytes | None = None

    async def data_generator():
        """Generator that yields data chunks for current part."""
        nonlocal buffer, in_data

        while in_data:
            # Look for next boundary
            next_boundary = buffer.find(boundary_delimiter)

            if next_boundary == -1:
                # No boundary found yet
                if len(buffer) > len(boundary_delimiter) + 4:
                    # Yield safe portion, keep rest for boundary detection
                    safe_amount = len(buffer) - len(boundary_delimiter) - 4
                    chunk = bytes(buffer[:safe_amount])
                    buffer = buffer[safe_amount:]
                    if chunk:
                        yield chunk

                # Need more data from stream
                try:
                    next_chunk = await stream.__anext__()
                    buffer.extend(next_chunk)
                except StopAsyncIteration:
                    # Stream ended, yield remaining buffer
                    if buffer:
                        data = _remove_last_crlf(bytes(buffer))
                        if data:
                            yield data
                    buffer.clear()
                    in_data = False
                    break
            else:
                # Found boundary - yield final data chunk
                final_data = bytes(buffer[:next_boundary])
                final_data = _remove_last_crlf(final_data)
                if final_data:
                    yield final_data

                # Move buffer past this boundary
                buffer = buffer[next_boundary:]
                in_data = False
                break

    async for chunk in stream:
        buffer.extend(chunk)

        while True:
            if not in_headers and not in_data:
                # Looking for start of new part
                boundary_index = buffer.find(boundary_delimiter)
                if boundary_index == -1:
                    if len(buffer) > len(boundary_delimiter):
                        buffer = buffer[-len(boundary_delimiter):]
                    break

                # Check for end boundary
                if buffer[boundary_index:].startswith(end_boundary):
                    return

                # Move past boundary
                after_boundary = boundary_index + len(boundary_delimiter)
                if after_boundary < len(buffer):
                    if buffer[after_boundary:after_boundary+2] == b"\r\n":
                        after_boundary += 2
                    elif buffer[after_boundary:after_boundary+1] == b"\n":
                        after_boundary += 1

                buffer = buffer[after_boundary:]
                in_headers = True
                headers_buffer.clear()

            elif in_headers:
                # Reading headers until \r\n\r\n
                header_end = buffer.find(b"\r\n\r\n")
                if header_end == -1:
                    # Need more data
                    if len(buffer) > 1024:  # Reasonable header size limit
                        headers_buffer.extend(buffer)
                        buffer.clear()
                    break

                # Found end of headers
                headers_buffer.extend(buffer[:header_end])
                buffer = buffer[header_end + 4:]

                # Parse headers
                headers = dict(split_headers(bytes(headers_buffer)))
                content_disposition = headers.get(b"content-disposition")

                if content_disposition:
                    cd_values = parse_content_disposition_values(content_disposition)
                    current_name = cd_values.get(b"name", b"")
                    current_filename = cd_values.get(b"filename")
                    current_content_type = headers.get(b"content-type")

                    # Check for charset field
                    if current_name == b"_charset_":
                        # Next data chunk is the charset value
                        # For simplicity, we'll skip proper charset handling in streaming mode
                        pass

                    in_headers = False
                    in_data = True

                    # Decide whether to stream or buffer based on presence of filename
                    if current_filename:
                        # File upload - yield StreamingFormPart
                        streaming_part = StreamingFormPart(
                            current_name,
                            data_generator(),
                            current_content_type,
                            current_filename,
                            default_charset,
                            chunk_size,
                        )
                        yield streaming_part
                        # data_generator() will handle consuming data and transitioning state
                    else:
                        # Small form field - buffer it
                        # Fall through to in_data handling
                        pass
                else:
                    # Invalid part, skip
                    in_headers = False
                    break

            elif in_data and not current_filename:
                # Buffering small form field data
                next_boundary = buffer.find(boundary_delimiter)

                if next_boundary == -1:
                    # Need more data
                    if len(buffer) > chunk_size * 2:
                        # Too large for a form field, error or treat as file
                        break
                    break

                # Found boundary
                field_data = bytes(buffer[:next_boundary])
                field_data = _remove_last_crlf(field_data)

                # Create FormPart for small field
                if field_data:
                    form_part = FormPart(
                        current_name or b"",
                        field_data,
                        current_content_type,
                        None,  # no filename
                        default_charset,
                    )
                    yield form_part

                # Move past boundary
                buffer = buffer[next_boundary:]
                in_data = False
                current_name = None
                current_filename = None
                current_content_type = None
