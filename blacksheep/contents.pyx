cimport cython

import re
import uuid
import json
from inspect import isasyncgenfunction
from collections.abc import MutableSequence
from typing import Union, List, Optional, Callable, Any
from urllib.parse import parse_qsl
from urllib.parse import quote_plus


_charset_rx = re.compile(b'charset=\\s?([^;]+)')
_boundary_rx = re.compile(b'boundary=(.+)$', re.I)
_content_type_form_data_line_rx = re.compile(b'content-type:\\s?([^;]+)(?:(charset=\\s?([^;]+)))?', re.I)
_content_disposition_header_type_rx = re.compile(b'^content-disposition:\\s([^;]+)', re.I)
_content_disposition_header_name_rx = re.compile(b'\\sname="([^\\"]+)"', re.I)
_content_disposition_header_filename_rx = re.compile(b'\\sfilename="([^\\"]+)"', re.I)


cdef class Content:

    def __init__(self,
                 bytes content_type,
                 data: Union[Callable, bytes]):
        self.type = content_type

        if callable(data):
            self.generator = data
            self._is_generator_async = isasyncgenfunction(data)
            self.body = None
            self.length = -1
        else:
            self.body = data
            self.length = len(data)
            self.generator = None
            self._is_generator_async = False

    async def get_parts(self):
        if self.body:
            yield self.body
        else:
            if self._is_generator_async:
                async for chunk in self.generator():
                    yield chunk
            else:
                for chunk in self.generator():
                    yield chunk


cdef class TextContent(Content):

    def __init__(self, str text):
        super().__init__(b'text/plain; charset=utf-8', text.encode('utf8'))


cdef class HtmlContent(Content):

    def __init__(self, str html):
        super().__init__(b'text/html; charset=utf-8', html.encode('utf8'))


cdef class JsonContent(Content):

    def __init__(self, object data, dumps=json.dumps):
        super().__init__(b'application/json', dumps(data).encode('utf8'))


cdef dict parse_www_form_urlencoded(bytes content):
    # application/x-www-form-urlencoded
    cdef bytes key, value
    data = {}
    for key, value in parse_qsl(content):
        if key in data:
            data[key].append(value)
        else:
            data[key] = [value]
    return data


cpdef dict parse_www_form(bytes content):
    return parse_www_form_urlencoded(content)


cpdef bytes extract_multipart_form_data_boundary(bytes content_type):
    m = _boundary_rx.search(content_type)
    if not m:
        return None
    return m.group(1)


cpdef tuple parse_content_disposition_header(bytes header):
    # content-disposition: form-data; name="file1"; filename="a.txt"
    type_m = _content_disposition_header_type_rx.search(header)

    if not type_m:
        raise ValueError(f'Failed to parse content-disposition type: {header}')

    name_m = _content_disposition_header_name_rx.search(header)
    if not name_m:
        raise ValueError(f'Given content-disposition header does not contain required field name: {header}')

    file_name_m = _content_disposition_header_filename_rx.search(header)
    return type_m.group(1), name_m.group(1), file_name_m.group(1) if file_name_m else None


cpdef bytes remove_last_crlf(bytes data):
    if data[-2:] == b'\r\n':
        return data[:-2]
    if data[-1:] == b'\n':
        return data[:-1]
    return data


cpdef bytes remove_first_crlf(bytes data):
    if data[:2] == b'\r\n':
        return data[2:]
    if data[:1] == b'\n':
        return data[1:]
    return data


cpdef bytes remove_extreme_crlf(bytes data):
    return remove_last_crlf(remove_first_crlf(data))


cpdef list split_multipart_form_data_parts(bytes data):
    result = []
    cdef int j = 0
    cdef int k = 0
    cdef char c

    for i, c in enumerate(data):
        if c == 10:
            k += 1
            if k == 3:
                result.append(remove_extreme_crlf(data[j:]))
                return result

            result.append(data[j:i])
            j = i+1


cpdef list parse_multipart_form_data(bytes content, bytes boundary):
    cdef bytes part
    cdef list result = []
    cdef bytes default_charset = b'utf8'
    cdef:
        bytes charset
        bytes content_type
        bytes disposition_type
        bytes name
        bytes file_name

    for part in content.split(boundary):
        if part == b'' or part == b'--' or part == b'--\r' or part == b'--\r\n':
            continue

        parts = split_multipart_form_data_parts(part.lstrip(b'\r\n'))

        charset = None
        content_type = None
        disposition_type, name, file_name = parse_content_disposition_header(parts[0])

        if name == b'_charset_':
            # https://tools.ietf.org/html/rfc7578#section-4.6
            default_charset = parts[2]
            continue

        # NB: if a content-type is defined, the second line is populated, otherwise is an empty bytes b''
        if parts[1]:
            content_type_m = _content_type_form_data_line_rx.search(parts[1])
            if content_type_m:
                content_type = content_type_m.group(1)
                charset = content_type_m.group(2)
                if not charset and content_type == b'text/plain':
                    charset = default_charset

        result.append(FormPart(name, parts[2], content_type, file_name, charset))
    return result


cpdef void write_multipart_part(FormPart part, bytearray destination):
    # https://tools.ietf.org/html/rfc7578#page-4
    destination.extend(b'Content-Disposition: form-data; name="')
    destination.extend(part.name)
    destination.extend(b'"')
    if part.file_name:
        destination.extend(b'; filename="')
        destination.extend(part.file_name)
        destination.extend(b'"\r\n')
    if part.content_type:
        destination.extend(b'Content-Type: ')
        destination.extend(part.content_type)
    destination.extend(b'\r\n\r\n')
    destination.extend(part.data)
    destination.extend(b'\r\n')


cpdef bytes write_www_form_urlencoded(data: Union[dict, list]):
    # application/x-www-form-urlencoded
    if isinstance(data, list):
        values = data
    else:
        values = data.items()
    
    cdef list contents = []
    
    for key, value in values:
        if isinstance(value, MutableSequence):
            for item in value:
                contents.append(quote_plus(key) + '=' + quote_plus(str(item)))
        else:
            contents.append(quote_plus(key) + '=' + quote_plus(str(value)))
    return ('&'.join(contents)).encode('utf8')


cdef class FormContent(Content):

    def __init__(self, data: dict):
        super().__init__(b'application/x-www-form-urlencoded', write_www_form_urlencoded(data))


cdef class FormPart:

    def __init__(self,
                 bytes name,
                 bytes data,
                 bytes content_type: Optional[bytes]=None,
                 bytes file_name: Optional[bytes]=None,
                 bytes charset: Optional[bytes] = None):
        self.name = name
        self.data = data
        self.file_name = file_name
        self.content_type = content_type
        self.charset = charset

    def __repr__(self):
        return f'<FormPart {self.name} - at {id(self)}>'


cdef class MultiPartFormData(Content):

    def __init__(self, list parts):
        self.parts = parts
        self.boundary = b'------' + str(uuid.uuid4()).replace('-', '').encode()
        super().__init__(b'multipart/form-data; boundary=' + self.boundary, write_multipart_form_data(self))


cpdef bytes write_multipart_form_data(MultiPartFormData data):
    cdef bytearray contents = bytearray()
    cdef FormPart part
    for part in data.parts:
        contents.extend(b'--')
        contents.extend(data.boundary)
        contents.extend(b'\r\n')
        write_multipart_part(part, contents)
    contents.extend(b'--')
    contents.extend(data.boundary)
    contents.extend(b'--\r\n')
    return bytes(contents)




