from datetime import datetime
from typing import Optional


cpdef bytes datetime_to_cookie_format(object value):
    # TODO: can be 1P_JAR=2018-11-17-20; expires=Mon, 17-Dec-2018 20:05:34 GMT; path=/; domain=.google.pl
    return value.strftime('%a, %d %b %Y %H:%M:%S GMT').encode()


cpdef object datetime_from_cookie_format(bytes value):
    # TODO: can be 1P_JAR=2018-11-17-20; expires=Mon, 17-Dec-2018 20:05:34 GMT; path=/; domain=.google.pl
    return datetime.strptime(value.decode(), '%a, %d %b %Y %H:%M:%S GMT')


cdef class HttpCookie:

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

    def __repr__(self):
        return f'<HttpCookie {self.name} {self.value}>'


cpdef HttpCookie parse_cookie(bytes value):
    cdef bytes eq, expires, domain, path, part, max_age, k, v, lower_k, lower_part
    cdef bint http_only, secure
    cdef bytes same_site
    cdef list parts
    eq = b'='
    parts = value.split(b'; ')
    name, value = parts[0].split(eq)

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

    return HttpCookie(name,
                      value,
                      expires,
                      domain,
                      path,
                      http_only,
                      secure,
                      max_age,
                      same_site)
