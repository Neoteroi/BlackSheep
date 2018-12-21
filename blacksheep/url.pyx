import httptools


cdef class InvalidURL(Exception):
    def __init__(self, str message):
        super().__init__(message)


cdef class URL:

    def __init__(self, bytes value):
        cdef bytes schema

        if value and value[0] not in {47, 72, 104}:
            # avoid exception for relative paths not starting with b'/'
            value = b'/' + value
        try:
            parsed = httptools.parse_url(value)
        except httptools.parser.errors.HttpParserInvalidURLError:
            raise InvalidURL(value)
        schema = parsed.schema
        if schema and schema != b'https' and schema != b'http':
            raise InvalidURL(f'expected http or https schema')
        self.value = value or b''
        self.schema = schema
        self.host = parsed.host
        self.port = parsed.port
        self.path = parsed.path
        self.query = parsed.query
        self.fragment = parsed.fragment
        self.userinfo = parsed.userinfo
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

