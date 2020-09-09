import httptools
from httptools.parser import errors


cdef class InvalidURL(Exception):
    def __init__(self, str message):
        super().__init__(message)


cdef class URL:

    def __init__(self, bytes value):
        cdef bytes schema
        cdef object port

        try:
            parsed = httptools.parse_url(value)
        except errors.HttpParserInvalidURLError:
            raise InvalidURL(f'The value cannot be parsed as URL ({value.decode()})')
        schema = parsed.schema
        if schema and schema != b'https' and schema != b'http':
            raise InvalidURL(f'Expected http or https schema; got instead {schema.decode()} in ({value.decode()})')

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
