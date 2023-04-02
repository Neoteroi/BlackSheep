import httptools
from httptools.parser import errors


cdef class InvalidURL(Exception):
    def __init__(self, str message):
        super().__init__(message)


def valid_schema(schema):
    if schema and schema != b'https' and schema != b'http':
        raise InvalidURL(f'Expected http or https schema; got instead {schema.decode()}')


cdef class URL:

    def __init__(self, bytes value):
        cdef bytes schema
        cdef object port

        try:
            # if the value starts with a dot, prepend a slash;
            # urllib.parse urlparse handles those, while httptools raises
            # an exception
            if value and value[0] == 46:
                value = b"/" + value
            parsed = httptools.parse_url(value)
        except errors.HttpParserInvalidURLError:
            raise InvalidURL(f'The value cannot be parsed as URL ({value.decode()})')
        schema = parsed.schema
        valid_schema(schema)

        self.value = value or b''
        self.schema = schema
        self.host = parsed.host
        self.port = parsed.port or 0
        self.path = parsed.path
        self.query = parsed.query
        self.fragment = parsed.fragment
        self.is_absolute = parsed.schema is not None

    def __repr__(self):
        return f'<URL {self.value}>'

    def __str__(self):
        return self.value.decode()

    cpdef URL join(self, URL other):
        if other.is_absolute:
            raise ValueError(f'Cannot concatenate to an absolute URL ({self.value} + {other.value})')
        if self.query or self.fragment:
            raise ValueError('Cannot concatenate a URL with query or fragment to another URL portion')
        first_part = self.value
        other_part = other.value
        if first_part and other_part and first_part[-1] == 47 and other_part[0] == 47:
            return URL(first_part[:-1] + other_part)
        return URL(first_part + other_part)

    cpdef URL base_url(self):
        if not self.is_absolute:
            raise ValueError('This URL is relative. Cannot extract a base URL (without path).')
        cdef bytes base_url

        base_url = self.schema + b'://' + self.host

        if self.port != 0:
            if (self.schema == b'http' and self.port != 80) or (self.schema == b'https' and self.port != 443):
                base_url = base_url + b':' + str(self.port).encode()

        return URL(base_url)

    cpdef URL with_host(self, bytes host):
        cdef bytes query, fragment
        if not self.is_absolute:
            raise TypeError("Cannot generate a URL from a partial URL")
        query = b"?" + self.query if self.query else b""
        fragment = b"#" + self.fragment if self.fragment else b""
        return URL(self.schema + b"://" + host + self.path + query + fragment)

    cpdef URL with_query(self, bytes query):
        cdef bytes fragment
        query = b"?" + query if query else b""
        fragment = b"#" + self.fragment if self.fragment else b""
        if self.is_absolute:
            return URL(self.schema + b"://" + self.host + self.path + query + fragment)
        return URL(self.path + query + fragment)

    cpdef URL with_scheme(self, bytes schema):
        valid_schema(schema)

        if not self.is_absolute:
            raise TypeError("Cannot generate a URL from a partial URL")

        return URL(schema + self.value[len(self.schema):])

    def __add__(self, other):
        if isinstance(other, bytes):
            return self.join(URL(other))

        if isinstance(other, URL):
            return self.join(other)
        return NotImplemented

    def __eq__(self, other):
        if isinstance(other, URL):
            return self.value == other.value
        return NotImplemented


cpdef URL build_absolute_url(
    bytes scheme,
    bytes host,
    bytes base_path,
    bytes path
):
    valid_schema(scheme)
    return URL(
        scheme
        + b"://"
        + host
        + (b"/" if base_path else b"") + base_path.lstrip(b"/").rstrip(b"/")
        + (b"/" if path else b"") + path.lstrip(b"/")
    )
