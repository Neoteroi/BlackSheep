import pytest
from typing import Tuple, Optional, Generator
from blacksheep.contents import FormPart
from .examples.multipart import FIELDS_THREE_VALUES, FIELDS_WITH_CARRIAGE_RETURNS, FIELDS_WITH_SMALL_PICTURE


def get_boundary(value: bytes):
    return value[:value.index(b'\n')+1]


def split_multipart(value: bytes):
    """Splits a whole multipart/form-data payload into single parts without boundary."""
    value = value.strip(b' ')
    boundary = value[:value.index(b'\n')].rstrip(b'\r')

    for part in value.split(boundary):
        part = part.strip(b'\r\n')
        if part == b'' or part == b'--':
            continue
        yield part


def split_headers(value: bytes):
    """Splits a whole portion of multipart form data representing headers into name, value pairs"""
    #
    # Examples of whole portions:
    #
    # Content-Disposition: form-data; name="two"
    # Content-Disposition: form-data; name="file_example"; filename="example-001.png"\r\nContent-Type: image/png
    #
    for raw_header in value.split(b'\r\n'):
        header_name, header_value = raw_header.split(b':', 1)
        yield header_name.lower(), header_value.lstrip(b' ')


def split_content_disposition_values(value: bytes) -> Tuple[bytes, Optional[bytes]]:
    """Parses a single header into key, value pairs"""
    for part in value.split(b';'):
        if b'=' in part:
            name, value = part.split(b'=', 1)
            yield name.lower().strip(b' '), value.strip(b'" ')
        else:
            yield 'type', part


def parse_content_disposition_values(value: bytes):
    return dict(split_content_disposition_values(value))


class CharsetPart(Exception):

    def __init__(self, default_charset: bytes):
        self.default_charset = default_charset


def parse_part(value: bytes, default_charset: Optional[bytes]) -> FormPart:
    """Parses a single multipart/form-data part."""
    raw_headers, data = value.split(b'\r\n\r\n', 1)

    headers = dict(split_headers(raw_headers))

    content_disposition = headers.get(b'content-disposition')

    if not content_disposition:
        # what to do? raise makes sense
        raise Exception('Missing Content-Disposition header in multipart/form-data part.')

    content_disposition_values = parse_content_disposition_values(content_disposition)

    field_name = content_disposition_values.get(b'name')

    if field_name == b'_charset_':
        # TODO: set default charset!
        raise CharsetPart(data)
    #
    # NB: a charset is passed as a whole part!!
    #
    content_type = None
    charset = None or default_charset ## TODO!
    # TODO: use string for file name and name?
    return FormPart(field_name,
                    data,
                    content_type,
                    content_disposition_values.get(b'filename'),
                    charset)


def parse_multipart(value: bytes):

    # NB: handling charset...
    # https://tools.ietf.org/html/rfc7578#section-4.6
    default_charset = None

    for part_bytes in split_multipart(value):

        try:
            yield parse_part(part_bytes, default_charset)
        except CharsetPart as charset:
            default_charset = charset.default_charset


@pytest.mark.parametrize('value', [
    FIELDS_THREE_VALUES,
    FIELDS_WITH_CARRIAGE_RETURNS,
    FIELDS_WITH_SMALL_PICTURE
])
def test_function(value):

    for part in parse_multipart(value):
        print(part)


"""

    # TODO: handle!!
    if field_name == b'_charset_':
        # https://tools.ietf.org/html/rfc7578#section-4.6
        # default_charset = parts[2]
        ...
        
       --AaB03x
       content-disposition: form-data; name="_charset_"

       iso-8859-1
       --AaB03x--
       content-disposition: form-data; name="field1"

       ...text encoded in iso-8859-1 ...
       AaB03x--
"""
