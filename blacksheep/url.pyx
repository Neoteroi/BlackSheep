# cython: language_level=3, boundscheck=False, nonecheck=False

from cpython.bytes cimport (
    PyBytes_AS_STRING,
    PyBytes_GET_SIZE,
    PyBytes_FromStringAndSize,
)
from . cimport url_cparser as uparser

from cpython.mem cimport PyMem_Malloc, PyMem_Free
from cpython.unicode cimport PyUnicode_FromStringAndSize
from libc.string cimport memcpy
cdef extern from "Python.h":
    const char* PyUnicode_AsUTF8AndSize(object, Py_ssize_t*)

cdef inline bint is_valid_schema(const char* s, Py_ssize_t n):
    if n == 4:
        return (s[0]==104 and s[1]==116 and s[2]==116 and s[3]==112)
    elif n == 5:
        return (s[0]==104 and s[1]==116 and s[2]==116 and
                s[3]==112 and s[4]==115)
    return 0

cdef inline void validate_schema(const char* s, Py_ssize_t n):
    cdef bytes msg
    cdef bint is_valid = is_valid_schema(s,n)
    if is_valid is False:
        msg = PyBytes_FromStringAndSize(s, n)
        raise InvalidURL(f"Expected 'http' or 'https'; got '{msg.decode()}'")

cdef class InvalidURL(Exception):
    """Raised on invalid URL or wrong schema."""
    pass

cdef class URL:
    # All cdef readonly attrs (value, schema, host, port,
    # path, query, fragment, is_absolute) are in url.pxd

    def __init__(self, bytes value):
        cdef uparser.http_parser_url parsed
        cdef int res, off, ln
        cdef char* buf
        cdef Py_ssize_t buf_len

        # normalize leading-dot paths (“./foo” → “/./foo”)
        if value and value[0] == 46:
            value = b"/" + value
        self.value = value or b""

        # grab raw pointer & length
        buf     = <char*>PyBytes_AS_STRING(self.value)
        buf_len = PyBytes_GET_SIZE(self.value)

        # parse in C
        uparser.http_parser_url_init(&parsed)
        res = uparser.http_parser_parse_url(buf, buf_len, 0, &parsed)
        if res != 0:
            raise InvalidURL(f"Invalid URL: {self.value!r}")

        # SCHEMA
        if parsed.field_set & (1 << uparser.UF_SCHEMA):
            off = parsed.field_data[<int>uparser.UF_SCHEMA].off
            ln  = parsed.field_data[<int>uparser.UF_SCHEMA].len
            self.schema = <bytes>PyBytes_FromStringAndSize(buf + off, ln)
            self.is_absolute = True
            validate_schema(
                <char*>PyBytes_AS_STRING(self.schema),
                PyBytes_GET_SIZE(self.schema),
            )
        else:
            self.schema = None
            self.is_absolute = False

        # HOST
        if parsed.field_set & (1 << uparser.UF_HOST):
            off = parsed.field_data[<int>uparser.UF_HOST].off
            ln  = parsed.field_data[<int>uparser.UF_HOST].len
            self.host = <bytes>PyBytes_FromStringAndSize(buf + off, ln)
        else:
            self.host = None

        # PORT
        self.port = parsed.port if parsed.field_set & (1 << uparser.UF_PORT) else 0

        # PATH
        if parsed.field_set & (1 << uparser.UF_PATH):
            off = parsed.field_data[<int>uparser.UF_PATH].off
            ln  = parsed.field_data[<int>uparser.UF_PATH].len
            self.path = <bytes>PyBytes_FromStringAndSize(buf + off, ln)
        else:
            self.path = None

        # QUERY
        if parsed.field_set & (1 << uparser.UF_QUERY):
            off = parsed.field_data[<int>uparser.UF_QUERY].off
            ln  = parsed.field_data[<int>uparser.UF_QUERY].len
            self.query = <bytes>PyBytes_FromStringAndSize(buf + off, ln)
        else:
            self.query = None

        # FRAGMENT
        if parsed.field_set & (1 << uparser.UF_FRAGMENT):
            off = parsed.field_data[<int>uparser.UF_FRAGMENT].off
            ln  = parsed.field_data[<int>uparser.UF_FRAGMENT].len
            self.fragment = <bytes>PyBytes_FromStringAndSize(buf + off, ln)
        else:
            self.fragment = None

    def __repr__(self):
        return f"<URL {self.value!r}>"

    def __str__(self):
        return self.value.decode()

    cpdef URL join(self, URL other):
        if other.is_absolute:
            raise ValueError(f"Cannot join absolute URL: {other}")
        if self.query or self.fragment:
            raise ValueError("Base URL must not have query or fragment")
        cdef bytes a = self.value
        cdef bytes b = other.value
        if a and b and a[-1] == 47 and b[0] == 47:
            return URL(a[:-1] + b)
        return URL(a + b)

    cpdef URL base_url(self):
        if not self.is_absolute:
            raise ValueError("Relative URL has no base")
        cdef bytes result = self.schema + b"://" + self.host
        if self.port and not (
            (self.schema == b"http"  and self.port == 80) or
            (self.schema == b"https" and self.port == 443)
        ):
            result += b":" + str(self.port).encode()
        return URL(result)

    cpdef URL with_host(self, bytes host):
        if not self.is_absolute:
            raise TypeError("Cannot set host on a relative URL")
        cdef bytes q = b"?" + self.query   if self.query   else b""
        cdef bytes f = b"#" + self.fragment if self.fragment else b""
        return URL(self.schema + b"://" + host + self.path + q + f)

    cpdef URL with_query(self, bytes query):
        cdef bytes q = b"?" + query        if query        else b""
        cdef bytes f = b"#" + self.fragment if self.fragment else b""
        if self.is_absolute:
            return URL(self.schema + b"://" + self.host + self.path + q + f)
        return URL(self.path + q + f)

    cpdef URL with_scheme(self, bytes scheme):
        cdef char* sdata = <char*>PyBytes_AS_STRING(scheme)
        cdef Py_ssize_t slen = PyBytes_GET_SIZE(scheme)
        validate_schema(sdata, slen)
        if not self.is_absolute:
            raise TypeError("Cannot set scheme on a relative URL")
        return URL(scheme + self.value[len(self.schema):])

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

            cdef const char *schemab
            cdef const char *hostb 
            cdef const char *bp
            cdef const char *pb
            cdef Py_ssize_t sl, hl, bpl, pl
            cdef Py_ssize_t off_bp_start, off_bp_end, len_base_clean
            cdef Py_ssize_t off_p_start, off_p_end, len_path_clean
            cdef bint has_base, has_path
            cdef Py_ssize_t tot_length, pos
            cdef char *buf
            cdef bytes url_bytes

            # Obtain raw buffers & lengths
            schemab = <char*>PyBytes_AS_STRING(scheme)
            sl      = PyBytes_GET_SIZE(scheme)
            hostb   = <char*>PyBytes_AS_STRING(host)
            hl      = PyBytes_GET_SIZE(host)
            bp      = <char*>PyBytes_AS_STRING(base_path)
            bpl     = PyBytes_GET_SIZE(base_path)
            pb      = <char*>PyBytes_AS_STRING(path)
            pl      = PyBytes_GET_SIZE(path)

            # Validate scheme
            validate_schema(schemab, sl)

            # Clean base_path (strip leading/trailing '/')
            if bpl == 0:
                off_bp_start = off_bp_end = 0
                has_base     = False
            else:
                off_bp_start = 0
                while off_bp_start < bpl and bp[off_bp_start] == <char>47:
                    off_bp_start += 1
                off_bp_end = bpl
                while off_bp_end > off_bp_start and bp[off_bp_end-1] == <char>47:
                    off_bp_end -= 1
                len_base_clean = off_bp_end - off_bp_start
                has_base       = (len_base_clean > 0)

            # Clean path (strip leading/trailing '/')
            if pl == 0:
                off_p_start = off_p_end = 0
                has_path    = False
            else:
                off_p_start = 0
                while off_p_start < pl and pb[off_p_start] == <char>47:
                    off_p_start += 1
                off_p_end = pl
                while off_p_end > off_p_start and pb[off_p_end-1] == <char>47:
                    off_p_end -= 1
                len_path_clean = off_p_end - off_p_start
                has_path       = (len_path_clean > 0)

            # Calculate total length: scheme + "://" + host + ["/"+base] + ["/"+path]
            tot_length = sl + 3 + hl
            if has_base:
                tot_length += 1 + len_base_clean
            if has_path:
                tot_length += 1 + len_path_clean

            # Allocate buffer
            buf = <char*>PyMem_Malloc(tot_length)
            pos = 0

            # scheme
            memcpy(buf + pos, schemab, sl)
            pos += sl
            buf[pos] = <char>58   # ':' == 58
            pos += 1
            buf[pos] = <char>47   # '/' == 47
            pos += 1
            buf[pos] = <char>47   # '/' == 47
            pos += 1

            # host
            memcpy(buf + pos, hostb, hl)
            pos += hl

            # base_path
            if has_base:
                buf[pos] = <char>47
                pos += 1
                memcpy(buf + pos, bp + off_bp_start, len_base_clean)
                pos += len_base_clean

            # path
            if has_path:
                buf[pos] = <char>47
                pos += 1
                memcpy(buf + pos, pb + off_p_start, len_path_clean)
                pos += len_path_clean

            # Form Python bytes and wrap in URL
            url_bytes = PyBytes_FromStringAndSize(buf, tot_length)
            PyMem_Free(buf)
            return URL(url_bytes)





cpdef str join_prefix(str prefix, str path):
        """
        Cython-optimized join_prefix working on UTF-8 char* buffers.
        No .strip(), no .endswith().
        """
        cdef const char *p_buf
        cdef Py_ssize_t p_len
        cdef const char *pa_buf
        cdef Py_ssize_t pa_len
        cdef Py_ssize_t p_end, pa_start, pa_end, pc_len, res_len
        cdef bint trailing
        cdef char *res_buf
        cdef str result

        # Get raw UTF-8 pointers & lengths
        p_buf  = PyUnicode_AsUTF8AndSize(prefix, &p_len)
        pa_buf = PyUnicode_AsUTF8AndSize(path,   &pa_len)

        # Compute prefix_clean length (p_end)
        if p_len == 1 and p_buf[0] == <char>47:  # '/'
            p_end = 0
        else:
            p_end = p_len
            while p_end > 0 and p_buf[p_end-1] == <char>47:
                p_end -= 1

        # Compute path_clean start/end and trailing flag
        if pa_len == 1 and pa_buf[0] == <char>47:
            pa_start = 0
            pa_end   = 0
            trailing = True
        else:
            trailing = (pa_len > 0 and pa_buf[pa_len-1] == <char>47)
            pa_start = 0
            while pa_start < pa_len and pa_buf[pa_start] == <char>47:
                pa_start += 1
            pa_end = pa_len
            while pa_end > pa_start and pa_buf[pa_end-1] == <char>47:
                pa_end -= 1

        pc_len = pa_end - pa_start

        # Case 1: both empty → "/"
        if p_end == 0 and pc_len == 0:
            return "/"

        # Case 2: only path → "/" + path_clean (+ trailing "/")
        if p_end == 0:
            res_len = 1 + pc_len + (1 if trailing and pc_len > 0 else 0)
            res_buf = <char*>PyMem_Malloc(res_len)
            res_buf[0] = <char>47
            if pc_len > 0:
                memcpy(res_buf + 1, pa_buf + pa_start, pc_len)
                if trailing:
                    res_buf[1 + pc_len] = <char>47
            result = PyUnicode_FromStringAndSize(res_buf, res_len)
            PyMem_Free(res_buf)
            return result

        # Case 3: only prefix → prefix_clean
        if pc_len == 0:
            result = PyUnicode_FromStringAndSize(p_buf, p_end)
            return result

        # Case 4: both present → prefix_clean + "/" + path_clean (+ trailing "/")
        res_len = p_end + 1 + pc_len + (1 if trailing else 0)
        res_buf = <char*>PyMem_Malloc(res_len)
        memcpy(res_buf, p_buf, p_end)
        res_buf[p_end] = <char>47
        memcpy(res_buf + p_end + 1, pa_buf + pa_start, pc_len)
        if trailing:
            res_buf[p_end + 1 + pc_len] = <char>47
        result = PyUnicode_FromStringAndSize(res_buf, res_len)
        PyMem_Free(res_buf)
        return result
