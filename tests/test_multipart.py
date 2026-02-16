from io import BytesIO
from typing import BinaryIO
import pytest

from blacksheep.contents import MultiPartFormData
from blacksheep.multipart import (
    FormPart,
    _remove_last_crlf,
    parse_multipart,
    parse_multipart_async,
    parse_part,
)

from .examples.multipart import (
    FIELDS_THREE_VALUES,
    FIELDS_WITH_CARRIAGE_RETURNS,
    FIELDS_WITH_CARRIAGE_RETURNS_AND_DEFAULT_CHARSET,
    FIELDS_WITH_SMALL_PICTURE,
)


@pytest.mark.parametrize(
    "value,expected_value",
    [
        [
            FIELDS_THREE_VALUES,
            [
                FormPart(b"one", b"aaa"),
                FormPart(b"one", b"bbb"),
                FormPart(b"two", b"ccc"),
                FormPart(b"two", b"daup"),
                FormPart(b"Submit", b"Submit"),
            ],
        ],
        [
            FIELDS_WITH_CARRIAGE_RETURNS,
            [
                FormPart(b"one", b"AA"),
                FormPart(b"one", b"BB"),
                FormPart(b"two", b"CC"),
                FormPart(b"two", b"DD"),
                FormPart(
                    b"description",
                    "Hello\r\n\r\nThis contains øø\r\n\r\nCarriage returns".encode(
                        "utf8"
                    ),
                ),
                FormPart(b"Submit", b"Submit"),
            ],
        ],
        [
            FIELDS_WITH_CARRIAGE_RETURNS_AND_DEFAULT_CHARSET,
            [
                FormPart(b"one", b"AA"),
                FormPart(b"two", b"CC", charset=b"iso-8859-1"),
                FormPart(b"two", b"DD", charset=b"iso-8859-1"),
                FormPart(
                    b"description",
                    "Hello\r\n\r\nThis contains øø\r\n\r\nCarriage returns".encode(
                        "iso-8859-1"
                    ),
                    charset=b"iso-8859-1",
                ),
                FormPart(
                    b"album", "ØØ Void".encode("iso-8859-1"), charset=b"iso-8859-1"
                ),
            ],
        ],
        [
            FIELDS_WITH_SMALL_PICTURE,
            [
                FormPart(b"one", b"aaa"),
                FormPart(b"one", b"bbb"),
                FormPart(b"two", b"ccc"),
                FormPart(b"two", b"example"),
                FormPart(
                    b"file_example",
                    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x08\x00\x00\x00\x08"
                    b"\x08\x06\x00\x00\x00\xc4\x0f\xbe\x8b\x00\x00\x01\x84iCCPICC profile\x00\x00("
                    b"\x91}\x91=H\xc3@\x1c\xc5_S\xa5R\xaa\x0ev\x90\xe2\x90\xa1:Y\x10\x15q\x94*\x16\xc1Bi+\xb4"
                    b"\xea`r\xe9\x174iHR\\\x1c\x05\xd7\x82\x83\x1f\x8bU\x07\x17g]\x1d\\\x05A\xf0\x03\xc4\xc5"
                    b"\xd5I\xd1EJ\xfc_Rh\x11\xe3\xc1q?\xde\xdd{"
                    b'\xdc\xbd\x03\x84f\x95\xa9f\xcf\x04\xa0j\x96\x91N\xc4\xc5\\~U\x0c\xbc"\x08?\x06\x10'
                    b"\x81Ob\xa6\x9e\xcc,"
                    b"f\xe19\xbe\xee\xe1\xe3\xeb]\x8cgy\x9f\xfbs\xf4+\x05\x93\x01>\x91x\x8e\xe9\x86E\xbcA"
                    b"<\xb3i\xe9\x9c\xf7\x89\xc3\xac,"
                    b")\xc4\xe7\xc4\xe3\x06]\x90\xf8\x91\xeb\xb2\xcbo\x9cK\x0e\x0b<3ld\xd3\xf3\xc4ab\xb1\xd4"
                    b"\xc5r\x17\xb3\xb2\xa1\x12O\x13G\x15U\xa3|!\xe7\xb2\xc2y\x8b\xb3Z\xad\xb3\xf6=\xf9\x0bC"
                    b"\x05m%\xc3u\x9a#H`\tI\xa4 "
                    b'BF\x1d\x15Ta!F\xabF\x8a\x894\xed\xc7=\xfc\x11\xc7\x9f"\x97L\xae\n\x189\x16P\x83\n\xc9'
                    b"\xf1\x83\xff\xc1\xefn\xcd\xe2\xd4\xa4\x9b\x14\x8a\x03\xbd/\xb6\xfd1\n\x04v\x81V\xc3\xb6"
                    b"\xbf\x8fm\xbbu\x02\xf8\x9f\x81+\xad\xe3\xaf5\x81\xd9O\xd2\x1b\x1d-z\x04\x0cn\x03\x17"
                    b"\xd7\x1dM\xde\x03.w\x80\xe1']2$G\xf2\xd3\x14\x8aE\xe0\xfd\x8c\xbe)\x0f\x0c\xdd\x02"
                    b"\xc15\xb7\xb7\xf6>N\x1f\x80,"
                    b"u\xb5|\x03\x1c\x1c\x02c%\xca^\xf7xw_wo\xff\x9ei\xf7\xf7\x03\x0e\xd5r\x7fYl\xff3\x00\x00"
                    b'\x00\x06bKGD\x00\x03\x00\x1a\x00\x1f"Z\xea\xfc\x00\x00\x00\tpHYs\x00\x00.#\x00\x00'
                    b".#\x01x\xa5?v\x00\x00\x00\x07tIME\x07\xe3\n\x03\x0e\x1e\x0fJa{"
                    b"\x87\x00\x00\x00\x19tEXtComment\x00Created with "
                    b"GIMPW\x81\x0e\x17\x00\x00\x00nIDAT\x18\xd3c0\xdan\xf4?.\x98\xe1\xff\x83`\x86\xff\x01"
                    b".+\xff/\x98\xf6\xfc\xff\xcd7~\xff\x95["
                    b"\x8b\xff\xd7\xbd\xb8\xfa\x9f\x01\x9f$\xb3\x94\xfc\x7f\x06|\x92\xccR\xf2\xff\x19\xf0I2K"
                    b"\xc9\xffg\xc0'\xc9,"
                    b"%\xff\x9f\xf1\xe6\x1b\xbf\xff^3U\x19\xa2\x93\x93\x18Z\x8d\xbc\x18\xd0\x01\x13>I\x06\x06"
                    b"\x06\x06\xc6\xba\x17W\xff\xe3\x92d```\x00\x00+\x05h|\x7f\xbaa\x83\x00\x00\x00\x00IEND"
                    b"\xaeB`\x82",
                    b"image/png",
                    b"example-001.png",
                    None,
                ),
                FormPart(b"description", b"Beee\r\n\r\nBeeeeee!"),
                FormPart(b"Submit", b"Submit"),
            ],
        ],
    ],
)
def test_function(value: bytes, expected_value):
    values = list(parse_multipart(value))
    assert values == expected_value


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


def test_parse_part_raises_for_missing_content_disposition():
    with pytest.raises(ValueError):
        parse_part(
            b'X-Content: form-data; name="one"\r\n\r\naaa',
            None,
        )


async def test_parse_multipart_async():
    data = MultiPartFormData([FormPart(b"a", b"world"), FormPart(b"b", b"9000")])

    async def stream():
        async for chunk in data.stream():
            yield chunk

    parts = []
    async for part in parse_multipart_async(stream(), data.boundary):
        # Consume the part data to ensure proper streaming
        data_chunks = []
        async for chunk in part.stream():
            data_chunks.append(chunk)
        part_data = b"".join(data_chunks)
        parts.append((part.name, part_data))

    assert len(parts) == 2
    assert parts[0] == ("a", b"world")
    assert parts[1] == ("b", b"9000")


async def test_multipart_write_1():
    file = BytesIO()
    file.write(b"Hello, World!")

    content = MultiPartFormData([
        FormPart.field(
            "description",
            "Important documents for review",
        ),
        FormPart.from_file(
            "attachment",
            "example.txt",
            file=file
        ),
    ])

    i = 0
    async for part in parse_multipart_async(content.stream(), content.boundary):
        if i == 0:
            assert part.name == "description"
            assert part.content_type == "text/plain"
            assert part.charset == "utf-8"
            data = await part.read()
            assert data == b'Important documents for review'
        if i == 1:
            assert part.name == "attachment"
            assert part.file_name == "example.txt"

            data = await part.read()
            assert data == b"Hello, World!"
        i += 1


async def test_multipart_write_multiple_files():
    """Test uploading multiple files with text fields."""
    file1 = BytesIO()
    file1.write(b"Content of first file")

    file2 = BytesIO()
    file2.write(b"Content of second file")

    file3 = BytesIO()
    file3.write(b"Content of third file")

    content = MultiPartFormData([
        FormPart.field("title", "Multiple File Upload Test"),
        FormPart.from_file("file1", "document1.txt", file=file1),
        FormPart.field("category", "documents"),
        FormPart.from_file("file2", "document2.txt", file=file2),
        FormPart.from_file("file3", "document3.txt", file=file3),
    ])

    parts = []
    async for part in parse_multipart_async(content.stream(), content.boundary):
        data = await part.read()
        parts.append({
            "name": part.name,
            "data": data,
            "file_name": part.file_name,
            "content_type": part.content_type,
        })

    assert len(parts) == 5
    assert parts[0]["name"] == "title"
    assert parts[0]["data"] == b"Multiple File Upload Test"
    assert parts[1]["name"] == "file1"
    assert parts[1]["data"] == b"Content of first file"
    assert parts[1]["file_name"] == "document1.txt"
    assert parts[2]["name"] == "category"
    assert parts[2]["data"] == b"documents"
    assert parts[3]["name"] == "file2"
    assert parts[3]["data"] == b"Content of second file"
    assert parts[4]["name"] == "file3"
    assert parts[4]["data"] == b"Content of third file"


async def test_multipart_write_empty_file():
    """Test uploading an empty file."""
    empty_file = BytesIO()

    content = MultiPartFormData([
        FormPart.field("description", "Empty file upload"),
        FormPart.from_file("empty", "empty.txt", file=empty_file),
    ])

    parts = []
    async for part in parse_multipart_async(content.stream(), content.boundary):
        data = await part.read()
        parts.append({"name": part.name, "data": data})

    assert len(parts) == 2
    assert parts[0]["data"] == b"Empty file upload"
    assert parts[1]["data"] == b""


async def test_multipart_write_only_fields():
    """Test multipart form with only text fields, no files."""
    content = MultiPartFormData([
        FormPart.field("username", "john_doe"),
        FormPart.field("email", "john@example.com"),
        FormPart.field("age", "30"),
        FormPart.field("bio", "Software developer\nLoves coding"),
    ])

    parts = []
    async for part in parse_multipart_async(content.stream(), content.boundary):
        data = await part.read()
        parts.append((part.name, data.decode("utf-8")))

    assert len(parts) == 4
    assert parts[0] == ("username", "john_doe")
    assert parts[1] == ("email", "john@example.com")
    assert parts[2] == ("age", "30")
    assert parts[3] == ("bio", "Software developer\nLoves coding")


async def test_multipart_write_binary_data():
    """Test uploading binary data (simulating an image)."""
    # Simulate binary image data
    binary_data = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])  # PNG header
    binary_data += b"\x00" * 100  # Add some null bytes

    binary_file = BytesIO()
    binary_file.write(binary_data)

    content = MultiPartFormData([
        FormPart.field("image_name", "test_image"),
        FormPart.from_file("image", "test.png", file=binary_file),
    ])

    parts = []
    async for part in parse_multipart_async(content.stream(), content.boundary):
        data = await part.read()
        parts.append({
            "name": part.name,
            "data": data,
            "file_name": part.file_name,
        })

    assert len(parts) == 2
    assert parts[0]["data"] == b"test_image"
    assert parts[1]["data"] == binary_data
    assert parts[1]["file_name"] == "test.png"


async def test_multipart_write_large_content():
    """Test handling larger content."""
    large_text = "A" * 10000  # 10KB of text

    large_file = BytesIO()
    large_file.write(large_text.encode("utf-8"))

    content = MultiPartFormData([
        FormPart.field("size_info", "Large file test"),
        FormPart.from_file("large_file", "large.txt", file=large_file),
    ])

    parts = []
    async for part in parse_multipart_async(content.stream(), content.boundary):
        data = await part.read()
        parts.append({"name": part.name, "data": data})

    assert len(parts) == 2
    assert parts[0]["data"] == b"Large file test"
    assert parts[1]["data"] == large_text.encode("utf-8")
    assert len(parts[1]["data"]) == 10000


async def test_multipart_write_special_characters():
    """Test multipart form with special characters and Unicode."""
    content = MultiPartFormData([
        FormPart.field("name", "José García"),
        FormPart.field("emoji", "Hello 👋 World 🌍"),
        FormPart.field("symbols", "Special: @#$%^&*()_+-=[]{}|;:',.<>?/"),
        FormPart.field("multiline", "Line 1\nLine 2\r\nLine 3"),
    ])

    parts = []
    async for part in parse_multipart_async(content.stream(), content.boundary):
        data = await part.read()
        parts.append((part.name, data.decode("utf-8")))

    assert len(parts) == 4
    assert parts[0] == ("name", "José García")
    assert parts[1] == ("emoji", "Hello 👋 World 🌍")
    assert parts[2] == ("symbols", "Special: @#$%^&*()_+-=[]{}|;:',.<>?/")
    assert parts[3] == ("multiline", "Line 1\nLine 2\r\nLine 3")


async def test_multipart_write_mixed_content_types():
    """Test multipart form with various content types."""
    text_file = BytesIO()
    text_file.write(b"Plain text content")

    json_data = b'{"key": "value", "number": 42}'
    json_file = BytesIO()
    json_file.write(json_data)

    csv_data = b"name,age,city\nAlice,30,NYC\nBob,25,LA"
    csv_file = BytesIO()
    csv_file.write(csv_data)

    content = MultiPartFormData([
        FormPart.field("description", "Mixed content types"),
        FormPart.from_file("text_doc", "readme.txt", file=text_file),
        FormPart.from_file("json_doc", "data.json", file=json_file),
        FormPart.from_file("csv_doc", "data.csv", file=csv_file),
    ])

    parts = []
    async for part in parse_multipart_async(content.stream(), content.boundary):
        data = await part.read()
        parts.append({
            "name": part.name,
            "data": data,
            "file_name": part.file_name,
        })

    assert len(parts) == 4
    assert parts[0]["data"] == b"Mixed content types"
    assert parts[1]["data"] == b"Plain text content"
    assert parts[1]["file_name"] == "readme.txt"
    assert parts[2]["data"] == json_data
    assert parts[2]["file_name"] == "data.json"
    assert parts[3]["data"] == csv_data
    assert parts[3]["file_name"] == "data.csv"


async def test_multipart_field_name_with_quotes():
    """Test that field names containing double quotes are properly escaped.

    According to RFC 2183, double quotes in quoted strings must be escaped
    with a backslash: \"
    """
    content = MultiPartFormData([
        FormPart.field('field"name', "value1"),
        FormPart.field('my"field"with"quotes', "value2"),
    ])

    # Verify the encoded format contains escaped quotes
    encoded = b""
    async for chunk in content.stream():
        encoded += chunk

    # Field names should have escaped quotes: field\"name
    assert b'name="field\\"name"' in encoded
    assert b'name="my\\"field\\"with\\"quotes"' in encoded

    # Verify round-trip: parse back and get original field names
    parts = []
    async for part in parse_multipart_async(content.stream(), content.boundary):
        data = await part.read()
        parts.append((part.name, data.decode("utf-8")))

    assert len(parts) == 2
    assert parts[0] == ('field"name', "value1")
    assert parts[1] == ('my"field"with"quotes', "value2")


async def test_multipart_filename_with_quotes():
    """Test that filenames containing double quotes are properly escaped.

    According to RFC 2183, double quotes in quoted strings must be escaped
    with a backslash: \"
    """
    file1 = BytesIO()
    file1.write(b"Content 1")

    file2 = BytesIO()
    file2.write(b"Content 2")

    content = MultiPartFormData([
        FormPart.from_file("upload", 'file"name.txt', file=file1),
        FormPart.from_file("document", 'my"document"2024.pdf', file=file2),
    ])

    # Verify the encoded format contains escaped quotes
    encoded = b""
    async for chunk in content.stream():
        encoded += chunk

    # Filenames should have escaped quotes
    assert b'filename="file\\"name.txt"' in encoded
    assert b'filename="my\\"document\\"2024.pdf"' in encoded

    # Verify round-trip: parse back and get original filenames
    parts = []
    async for part in parse_multipart_async(content.stream(), content.boundary):
        data = await part.read()
        parts.append({
            "name": part.name,
            "file_name": part.file_name,
            "data": data,
        })

    assert len(parts) == 2
    assert parts[0]["file_name"] == 'file"name.txt'
    assert parts[0]["data"] == b"Content 1"
    assert parts[1]["file_name"] == 'my"document"2024.pdf'
    assert parts[1]["data"] == b"Content 2"


async def test_multipart_field_name_with_backslashes():
    """Test that field names containing backslashes are properly escaped.

    According to RFC 2183, backslashes in quoted strings must be escaped
    with another backslash: \\
    """
    content = MultiPartFormData([
        FormPart.field('field\\name', "value1"),
        FormPart.field('path\\to\\field', "value2"),
    ])

    # Verify the encoded format contains escaped backslashes
    encoded = b""
    async for chunk in content.stream():
        encoded += chunk

    # Backslashes should be escaped
    assert b'name="field\\\\name"' in encoded
    assert b'name="path\\\\to\\\\field"' in encoded

    # Verify round-trip
    parts = []
    async for part in parse_multipart_async(content.stream(), content.boundary):
        data = await part.read()
        parts.append((part.name, data.decode("utf-8")))

    assert len(parts) == 2
    assert parts[0] == ('field\\name', "value1")
    assert parts[1] == ('path\\to\\field', "value2")


async def test_multipart_filename_with_backslashes():
    """Test that filenames containing backslashes are properly escaped."""
    file1 = BytesIO()
    file1.write(b"Content")

    content = MultiPartFormData([
        FormPart.from_file("upload", 'path\\to\\file.txt', file=file1),
    ])

    # Verify the encoded format
    encoded = b""
    async for chunk in content.stream():
        encoded += chunk

    assert b'filename="path\\\\to\\\\file.txt"' in encoded

    # Verify round-trip
    parts = []
    async for part in parse_multipart_async(content.stream(), content.boundary):
        data = await part.read()
        parts.append({
            "file_name": part.file_name,
            "data": data,
        })

    assert len(parts) == 1
    assert parts[0]["file_name"] == 'path\\to\\file.txt'


async def test_multipart_quotes_and_backslashes_combined():
    """Test field names and filenames with both quotes and backslashes.

    This is the most complex case: both characters need escaping, and the
    backslash itself is the escape character.
    """
    file1 = BytesIO()
    file1.write(b"File content")

    content = MultiPartFormData([
        FormPart.field('field\\"name', "value1"),  # Contains backslash and quote
        FormPart.field('a"b\\c"d', "value2"),
        FormPart.from_file("upload", 'file\\"test".txt', file=file1),
    ])

    # Verify encoding
    encoded = b""
    async for chunk in content.stream():
        encoded += chunk

    # Both backslashes and quotes should be escaped
    # field\\"name becomes field\\\\"name (backslash->\\, quote->\")
    assert b'name="field\\\\\\"name"' in encoded
    # a"b\c"d becomes a\"b\\c\"d
    assert b'name="a\\"b\\\\c\\"d"' in encoded
    # file\\"test".txt becomes file\\\\"test\".txt
    assert b'filename="file\\\\\\"test\\".txt"' in encoded

    # Verify round-trip
    parts = []
    async for part in parse_multipart_async(content.stream(), content.boundary):
        data = await part.read()
        parts.append({
            "name": part.name,
            "file_name": part.file_name,
            "data": data.decode("utf-8") if part.file_name is None else data,
        })

    assert len(parts) == 3
    assert parts[0]["name"] == 'field\\"name'
    assert parts[0]["data"] == "value1"
    assert parts[1]["name"] == 'a"b\\c"d'
    assert parts[1]["data"] == "value2"
    assert parts[2]["file_name"] == 'file\\"test".txt'
    assert parts[2]["data"] == b"File content"
