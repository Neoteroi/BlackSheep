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


def _decode(value: bytes | None) -> str | None:
    if value is None:
        return value
    return value.decode("utf8")


async def parse_multipart_async(
    stream: AsyncIterable[bytes], boundary: bytes
) -> AsyncIterable[StreamingFormPart]:
    """
    Parses multipart/form-data from an async stream, yielding StreamingFormPart
    objects for all parts (both files and form fields).

    This implementation provides true streaming support for all multipart parts,
    allowing data to be read lazily without loading entire parts into memory.
    This is important not only for large file uploads, but also for large text
    fields that may be sent via multipart/form-data.

    IMPORTANT: Parts must be consumed (or explicitly skipped) in order before
    requesting the next part. If a part is not consumed before the next iteration,
    its data will be drained and discarded.

    Args:
        stream: Async iterable of byte chunks from the request body
        boundary: The boundary bytes from the Content-Type header

    Yields:
        StreamingFormPart objects for all parts (data accessed via stream() or read())

    Example:
        ```python
        async for part in parse_multipart_async(stream, boundary):
            if part.file_name:
                # File upload - stream to disk
                await part.save_to(f"uploads/{part.file_name.decode()}")
            else:
                # Form field - read value
                value = await part.read()
        ```
    """
    boundary_delimiter = b"--" + boundary
    end_boundary = boundary_delimiter + b"--"

    # Use manual iterator control to avoid buffering the entire stream
    stream_iter = stream.__aiter__()
    buffer = bytearray()
    default_charset = None

    # Track current part's data generator for draining if not consumed
    current_data_gen = None
    part_consumed = True

    async def read_more() -> bool:
        """Read more data from stream into buffer. Returns False if stream ended."""
        try:
            chunk = await stream_iter.__anext__()
            buffer.extend(chunk)
            return True
        except StopAsyncIteration:
            return False

    async def skip_to_boundary() -> bool:
        """
        Skip data until we find and move past a boundary delimiter.
        Returns False if end boundary reached or stream ended.
        """
        while True:
            # Check for end boundary first
            end_pos = buffer.find(end_boundary)
            if end_pos != -1:
                return False

            pos = buffer.find(boundary_delimiter)
            if pos != -1:
                # Move past the boundary
                after = pos + len(boundary_delimiter)

                # Ensure we have enough bytes to check for CRLF
                while len(buffer) < after + 2:
                    if not await read_more():
                        buffer[:] = buffer[after:] if len(buffer) > after else b""
                        return len(buffer) > 0

                # Skip CRLF after boundary
                if buffer[after : after + 2] == b"\r\n":
                    buffer[:] = buffer[after + 2 :]
                elif buffer[after : after + 1] == b"\n":
                    buffer[:] = buffer[after + 1 :]
                else:
                    buffer[:] = buffer[after:]
                return True

            # Keep minimal buffer for boundary detection, read more
            if len(buffer) > len(end_boundary):
                buffer[:] = buffer[-len(end_boundary) :]

            if not await read_more():
                return False

    async def data_generator():
        """Generator that yields data chunks for current part."""
        nonlocal part_consumed
        part_consumed = False

        try:
            while True:
                # Look for boundary in current buffer
                pos = buffer.find(boundary_delimiter)

                if pos != -1:
                    # Found boundary - yield data before it (minus trailing CRLF)
                    data = _remove_last_crlf(bytes(buffer[:pos]))
                    buffer[:] = buffer[pos:]  # Keep boundary for next part detection
                    if data:
                        yield data
                    return

                # No boundary found - yield safe portion of buffer
                # Keep enough bytes to detect boundary that might span chunks
                safe_threshold = len(boundary_delimiter) + 4
                if len(buffer) > safe_threshold:
                    safe_amount = len(buffer) - safe_threshold
                    chunk = bytes(buffer[:safe_amount])
                    buffer[:] = buffer[safe_amount:]
                    if chunk:
                        yield chunk

                # Read more data from stream
                if not await read_more():
                    # Stream ended - yield remaining buffer
                    if buffer:
                        data = _remove_last_crlf(bytes(buffer))
                        buffer.clear()
                        if data:
                            yield data
                    return
        finally:
            part_consumed = True

    async def drain_current_part():
        """Drain any unconsumed data from the current part."""
        nonlocal current_data_gen
        if current_data_gen is not None and not part_consumed:
            async for _ in current_data_gen:
                pass
        current_data_gen = None

    # Skip to first boundary
    if not await skip_to_boundary():
        return

    while True:
        # Drain previous part if caller didn't consume it
        await drain_current_part()

        # Check for end boundary marker ("--" after boundary)
        while len(buffer) < 2:
            if not await read_more():
                return
        if buffer[:2] == b"--":
            return

        # Read headers (until \r\n\r\n)
        while b"\r\n\r\n" not in buffer:
            if not await read_more():
                return

        header_end = buffer.find(b"\r\n\r\n")
        headers_data = bytes(buffer[:header_end])
        buffer[:] = buffer[header_end + 4 :]

        # Parse headers
        headers = dict(split_headers(headers_data))
        content_disposition = headers.get(b"content-disposition")

        if not content_disposition:
            # Invalid part - skip to next boundary
            if not await skip_to_boundary():
                return
            continue

        cd_values = parse_content_disposition_values(content_disposition)
        name = cd_values.get(b"name", b"")
        filename = cd_values.get(b"filename")
        content_type = headers.get(b"content-type")

        # Handle special _charset_ field
        if name == b"_charset_":
            charset_gen = data_generator()
            current_data_gen = charset_gen
            async for chunk in charset_gen:
                default_charset = chunk
                break
            await drain_current_part()
            if not await skip_to_boundary():
                return
            continue

        # Create data generator for this part
        current_data_gen = data_generator()

        # Yield the streaming part
        yield StreamingFormPart(
            _decode(name),
            current_data_gen,
            _decode(content_type),
            _decode(filename),
            _decode(default_charset),
        )

        # After yield returns (caller asked for next part), drain any unconsumed
        # data and skip to the next boundary
        await drain_current_part()
        if not await skip_to_boundary():
            return
