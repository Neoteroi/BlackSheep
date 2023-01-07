import pytest

from blacksheep.multipart import (
    FormPart,
    _remove_last_crlf,
    parse_multipart,
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
