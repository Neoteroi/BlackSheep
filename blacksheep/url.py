from urllib.parse import urlparse


class InvalidURL(Exception):
    def __init__(self, message: str):
        super().__init__(message)


def valid_schema(schema):
    if schema and schema != "https" and schema != "http":
        raise InvalidURL(f"Expected http or https schema; got instead {schema}")


class URL:
    def __init__(self, value: bytes):
        if not value:
            raise InvalidURL("Input empty or null.")
        try:
            if value and value[0] == 46:  # ord('.') == 46
                value = b"/" + value
            s = value.decode()
            parsed = urlparse(s)
        except Exception:
            raise InvalidURL(f"The value cannot be parsed as URL ({value.decode()})")
        schema = parsed.scheme
        valid_schema(schema)
        self.value = value or b""
        self.schema = schema.encode() if schema else None
        self.host = parsed.hostname.encode() if parsed.hostname else None
        self.port = parsed.port or 0
        self.path = parsed.path.encode() or b""
        self.query = parsed.query.encode() if parsed.query else None
        self.fragment = parsed.fragment.encode() if parsed.fragment else None
        self.is_absolute = bool(parsed.scheme)

    def __repr__(self):
        return f"<URL {self.value}>"

    def __str__(self):
        return self.value.decode()

    def join(self, other):
        if isinstance(other, bytes):
            other = URL(other)
        if other.is_absolute:
            raise ValueError(
                f"Cannot concatenate to an absolute URL ({self.value} + {other.value})"
            )
        if self.query or self.fragment:
            raise ValueError(
                "Cannot concatenate a URL with query or fragment to another URL portion"
            )
        first_part = self.value
        other_part = other.value
        if first_part and other_part and first_part[-1] == 47 and other_part[0] == 47:
            return URL(first_part[:-1] + other_part)
        return URL(first_part + other_part)

    def base_url(self):
        if not self.is_absolute:
            raise ValueError(
                "This URL is relative. Cannot extract a base URL (without path)."
            )
        base_url = f"{self.schema.decode()}://{self.host.decode()}"  # type: ignore
        if self.port != 0:
            if (self.schema == b"http" and self.port != 80) or (
                self.schema == b"https" and self.port != 443
            ):
                base_url = f"{base_url}:{self.port}"
        return URL(base_url.encode())

    def with_host(self, host: bytes):
        if not self.is_absolute:
            raise TypeError("Cannot generate a URL from a partial URL")
        query = b"?" + self.query if self.query else b""
        fragment = b"#" + self.fragment if self.fragment else b""
        url = f"{self.schema}://{host.decode()}{self.path}{query.decode()}{fragment.decode()}"
        return URL(url.encode())

    def with_query(self, query: bytes):
        query = b"?" + query if query else b""
        fragment = b"#" + self.fragment if self.fragment else b""
        if self.is_absolute:
            url = f"{self.schema}://{self.host}{self.path}{query.decode()}{fragment.decode()}"
            return URL(url.encode())
        url = f"{self.path}{query.decode()}{fragment.decode()}"
        return URL(url.encode())

    def with_scheme(self, schema: bytes):
        s = self.value.decode()
        if isinstance(schema, bytes):
            schema_str = schema.decode()
        else:
            schema_str = schema
        idx = s.find("://")
        if idx == -1:
            raise InvalidURL("Malformed URL for scheme replacement")
        # Ensure s is str, schema_str is str
        new_url = str(schema_str) + str(s[idx:])
        return URL(new_url.encode())

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


def build_absolute_url(scheme: bytes, host: bytes, base_path: bytes, path: bytes):
    scheme_str = scheme.decode() if isinstance(scheme, bytes) else scheme
    valid_schema(scheme_str)
    url = (
        str(scheme_str)
        + "://"
        + host.decode()
        + ("/" if base_path else "")
        + base_path.lstrip(b"/").rstrip(b"/").decode()
        + ("/" if path else "")
        + path.lstrip(b"/").decode()
    )
    return URL(url.encode())


def join_prefix(prefix: str, path: str) -> str:
    if not prefix:
        return path
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    if not path:
        return prefix + "/"
    if prefix[-1] == "/" and path[0] == "/":
        return prefix + path[1:]
    if prefix[-1] != "/" and path[0] != "/":
        return prefix + "/" + path
    return prefix + path
