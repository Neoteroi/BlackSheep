import pytest
from typing import List
from blacksheep import StreamedContent
from blacksheep.multipart import (
    parse_multipart,
    parse_content_disposition_values,
    get_boundary_from_header,
)
from blacksheep.contents import (
    parse_www_form,
    write_www_form_urlencoded,
    FormPart,
    MultiPartFormData,
    TextContent,
    HtmlContent,
)
from blacksheep.scribe import write_chunks


@pytest.mark.asyncio
async def test_chunked_encoding_with_generated_content():
    async def data_generator():
        yield b'{"hello":"world",'
        yield b'"lorem":'
        yield b'"ipsum","dolor":"sit"'
        yield b',"amet":"consectetur"}'

    content = StreamedContent(b"application/json", data_generator)

    chunks = []

    async for chunk in data_generator():
        chunks.append(chunk)

    gen = (item for item in chunks)

    async for chunk in write_chunks(content):
        try:
            generator_bytes = next(gen)
        except StopIteration:
            assert chunk == b"0\r\n\r\n"
        else:
            assert (
                chunk
                == hex(len(generator_bytes))[2:].encode()
                + b"\r\n"
                + generator_bytes
                + b"\r\n"
            )


@pytest.mark.parametrize(
    "content,expected_result",
    [
        [
            "Name=Gareth+Wylie&Age=24&Formula=a+%2B+b+%3D%3D+13%25%21",
            {"Name": "Gareth Wylie", "Age": "24", "Formula": "a + b == 13%!"},
        ],
        ["a=12&b=24&a=33", {"a": ["12", "33"], "b": "24"}],
    ],
)
def test_form_urlencoded_parser(content, expected_result):
    data = parse_www_form(content)
    assert expected_result == data


@pytest.mark.parametrize(
    "data,expected_result",
    [
        [
            {"Name": "Gareth Wylie", "Age": 24, "Formula": "a + b == 13%!"},
            b"Name=Gareth+Wylie&Age=24&Formula=a+%2B+b+%3D%3D+13%25%21",
        ],
        [[("a", "13"), ("a", "24"), ("b", "5"), ("a", "66")], b"a=13&a=24&b=5&a=66"],
        [{"a": [13, 24, 66], "b": [5]}, b"a=13&a=24&a=66&b=5"],
    ],
)
def test_form_urlencoded_writer(data, expected_result):
    content = write_www_form_urlencoded(data)
    assert expected_result == content


@pytest.mark.asyncio
async def test_multipart_form_data():
    data = MultiPartFormData(
        [
            FormPart(b"text1", b"text default"),
            FormPart(b"text2", "aωb".encode("utf8")),
            FormPart(b"file1", b"Content of a.txt.\r\n", b"text/plain", b"a.txt"),
            FormPart(
                b"file2",
                b"<!DOCTYPE html><title>Content of a.html.</title>\r\n",
                b"text/html",
                b"a.html",
            ),
            FormPart(
                b"file3", "aωb".encode("utf8"), b"application/octet-stream", b"binary"
            ),
        ]
    )

    whole = data.body

    expected_result_lines = [
        b"--" + data.boundary,
        b'Content-Disposition: form-data; name="text1"',
        b"",
        b"text default",
        b"--" + data.boundary,
        b'Content-Disposition: form-data; name="text2"',
        b"",
        "aωb".encode("utf8"),
        b"--" + data.boundary,
        b'Content-Disposition: form-data; name="file1"; filename="a.txt"',
        b"Content-Type: text/plain",
        b"",
        b"Content of a.txt.",
        b"",
        b"--" + data.boundary,
        b'Content-Disposition: form-data; name="file2"; filename="a.html"',
        b"Content-Type: text/html",
        b"",
        b"<!DOCTYPE html><title>Content of a.html.</title>",
        b"",
        b"--" + data.boundary,
        b'Content-Disposition: form-data; name="file3"; filename="binary"',
        b"Content-Type: application/octet-stream",
        b"",
        "aωb".encode("utf8"),
        b"--" + data.boundary + b"--",
        b"",
    ]

    assert whole == b"\r\n".join(expected_result_lines)


def test_parse_multipart_two_fields():
    content = (
        b'--------28cbeda4cdd04d1595b71933e31928cd\r\nContent-Disposition: form-data; name="a"\r\n\r\nworld\r\n'
        b'--------28cbeda4cdd04d1595b71933e31928cd\r\nContent-Disposition: form-data; name="b"\r\n\r\n9000\r\n'
        b"--------28cbeda4cdd04d1595b71933e31928cd--\r\n"
    )

    data = list(parse_multipart(content))  # type: List[FormPart]

    assert data is not None
    assert len(data) == 2

    assert data[0].name == b"a"
    assert data[0].data == b"world"
    assert data[1].name == b"b"
    assert data[1].data == b"9000"


def test_parse_multipart():
    boundary = b"---------------------0000000000000000000000001"

    content = b"\r\n".join(
        [
            boundary,
            b'Content-Disposition: form-data; name="text1"',
            b"",
            b"text default",
            boundary,
            b'Content-Disposition: form-data; name="text2"',
            b"",
            "aωb".encode("utf8"),
            boundary,
            b'Content-Disposition: form-data; name="file1"; filename="a.txt"',
            b"Content-Type: text/plain",
            b"",
            b"Content of a.txt.",
            b"",
            boundary,
            b'Content-Disposition: form-data; name="file2"; filename="a.html"',
            b"Content-Type: text/html",
            b"",
            b"<!DOCTYPE html><title>Content of a.html.</title>",
            b"",
            boundary,
            b'Content-Disposition: form-data; name="file3"; filename="binary"',
            b"Content-Type: application/octet-stream",
            b"",
            "aωb".encode("utf8"),
            boundary + b"--",
        ]
    )

    data = list(parse_multipart(content))  # type: List[FormPart]

    assert data is not None
    assert len(data) == 5

    assert data[0].name == b"text1"
    assert data[0].file_name is None
    assert data[0].content_type is None
    assert data[0].data == b"text default"

    assert data[1].name == b"text2"
    assert data[1].file_name is None
    assert data[1].content_type is None
    assert data[1].data == "aωb".encode("utf8")

    assert data[2].name == b"file1"
    assert data[2].file_name == b"a.txt"
    assert data[2].content_type == b"text/plain"
    assert data[2].data == b"Content of a.txt.\r\n"

    assert data[3].name == b"file2"
    assert data[3].file_name == b"a.html"
    assert data[3].content_type == b"text/html"
    assert data[3].data == b"<!DOCTYPE html><title>Content of a.html.</title>\r\n"

    assert data[4].name == b"file3"
    assert data[4].file_name == b"binary"
    assert data[4].content_type == b"application/octet-stream"
    assert data[4].data == "aωb".encode("utf8")


@pytest.mark.parametrize(
    "value, expected_result",
    [
        [
            b'form-data; name="file2"; filename="a.html"',
            {b"type": b"form-data", b"name": b"file2", b"filename": b"a.html"},
        ],
        [b'form-data; name="example"', {b"type": b"form-data", b"name": b"example"}],
        [
            b'form-data; name="hello-world"',
            {b"type": b"form-data", b"name": b"hello-world"},
        ],
    ],
)
def test_parsing_content_disposition_header(value, expected_result):
    parsed = parse_content_disposition_values(value)
    assert parsed == expected_result


@pytest.mark.parametrize(
    "value,expected_result",
    [
        (
            b"multipart/form-data; boundary=---------------------1321321",
            b"---------------------1321321",
        ),
        (
            b"multipart/form-data; boundary=--4ed15c90-6b4b-457f-99d8-e965c76679dd",
            b"--4ed15c90-6b4b-457f-99d8-e965c76679dd",
        ),
        (
            b"multipart/form-data; boundary=--4ed15c90-6b4b-457f-99d8-e965c76679dd",
            b"--4ed15c90-6b4b-457f-99d8-e965c76679dd",
        ),
        (
            b"multipart/form-data; boundary=-------------AAAA12345",
            b"-------------AAAA12345",
        ),
    ],
)
def test_extract_multipart_form_data_boundary(value, expected_result):
    boundary = get_boundary_from_header(value)
    assert boundary == expected_result


def test_html_content_type():
    content = HtmlContent("<html></html>")
    assert content.type == b"text/html; charset=utf-8"


@pytest.mark.parametrize("html", ["<html>ø</html>"])
def test_html_content_data(html):
    content = HtmlContent(html)
    assert content.body == html.encode("utf8")


def test_text_content_type():
    content = TextContent("Hello World")
    assert content.type == b"text/plain; charset=utf-8"


@pytest.mark.parametrize(
    "text", ["Zucchero Fornaciari - Papà perché", "Отава Ё - На речке, на речке"]
)
def test_text_content_data(text):
    content = TextContent(text)
    assert content.body == text.encode("utf8")
