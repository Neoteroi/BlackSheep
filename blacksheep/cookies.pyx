from typing import Optional
from datetime import datetime
from urllib.parse import quote, unquote


cpdef bytes datetime_to_cookie_format(object value):
    return value.strftime('%a, %d %b %Y %H:%M:%S GMT').encode()


cpdef object datetime_from_cookie_format(bytes value):
    value_str = value.decode()
    try:
        return datetime.strptime(value_str, '%a, %d %b %Y %H:%M:%S GMT')
    except ValueError:
        return datetime.strptime(value_str, '%a, %d-%b-%Y %H:%M:%S GMT')


cdef class Cookie:

    def __init__(self,
                 bytes name,
                 bytes value,
                 bytes expires=None,
                 bytes domain=None,
                 bytes path=None,
                 bint http_only=0,
                 bint secure=0,
                 bytes max_age=None,
                 bytes same_site=None):
        if not name:
            raise ValueError('A cookie name is required')
        self.name = name
        self.value = value
        self.expires = expires
        self._expiration = None
        self.domain = domain
        self.path = path
        self.http_only = http_only
        self.secure = secure
        self.max_age = max_age
        self.same_site = same_site

    cpdef Cookie clone(self):
        return Cookie(self.name,
                      self.value,
                      self.expires,
                      self.domain,
                      self.path,
                      self.http_only,
                      self.secure,
                      self.max_age,
                      self.same_site)

    @property
    def expiration(self):
        if not self.expires:
            return None

        if self._expiration is None:
            self._expiration = datetime_from_cookie_format(self.expires)
        return self._expiration

    @expiration.setter
    def expiration(self, value):
        self._expiration = value
        if value:
            self.expires = datetime_to_cookie_format(value)
        else:
            self.expires = None

    cpdef void set_max_age(self, int max_age):
        self.max_age = str(max_age).encode()

    def __repr__(self):
        return f'<Cookie {self.name.decode()}: {self.value.decode()}>'


cpdef Cookie parse_cookie(bytes value):
    cdef bytes eq, expires, domain, path, part, max_age, k, v, lower_k, lower_part
    cdef bint http_only, secure
    cdef bytes same_site
    cdef list parts
    eq = b'='
    parts = value.split(b'; ')
    if len(parts) == 0:
        try:
            name, value = value.split(eq)
        except ValueError as unpack_error:
            raise ValueError(f'Invalid name=value fragment: {parts[0]}')
        else:
            return Cookie(name, value)
    try:
        name, value = parts[0].split(eq)
    except ValueError as unpack_error:
        raise ValueError(f'Invalid name=value fragment: {parts[0]}')

    expires = None
    domain = None
    path = None
    http_only = False
    secure = False
    max_age = None
    same_site = None

    for part in parts:
        if eq in part:
            k, v = part.split(eq)
            lower_k = k.lower()
            if lower_k == b'expires':
                expires = v
            elif lower_k == b'domain':
                domain = v
            elif lower_k == b'path':
                path = v
            elif lower_k == b'max-age':
                max_age = v
            elif lower_k == b'samesite':
                same_site = v
        else:
            lower_part = part.lower()
            if lower_part == b'httponly':
                http_only = True
            if lower_part == b'secure':
                secure = True

    return Cookie(unquote(name.decode()).encode(),
                  unquote(value.decode()).encode(),
                  expires,
                  domain,
                  path,
                  http_only,
                  secure,
                  max_age,
                  same_site)
