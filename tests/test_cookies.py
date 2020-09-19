from datetime import datetime

import pytest

from blacksheep import (
    Cookie,
    datetime_from_cookie_format,
    datetime_to_cookie_format,
    parse_cookie,
    scribe,
)


COOKIES = [
    (b"Foo", b"Power", None, None, None, False, False, None, None, b"Foo=Power"),
    (
        b"Foo",
        b"Hello World;",
        None,
        None,
        None,
        False,
        False,
        None,
        None,
        b"Foo=Hello%20World%3B",
    ),
    (
        b"Foo; foo",
        b"Hello World;",
        None,
        None,
        None,
        False,
        False,
        None,
        None,
        b"Foo%3B%20foo=Hello%20World%3B",
    ),
    (
        b"Foo",
        b"Power",
        datetime(2018, 8, 17, 20, 55, 4),
        None,
        None,
        False,
        False,
        None,
        None,
        b"Foo=Power; Expires=Fri, 17 Aug 2018 20:55:04 GMT",
    ),
    (
        b"Foo",
        b"Power",
        datetime(2018, 8, 17, 20, 55, 4),
        b"something.org",
        None,
        False,
        False,
        None,
        None,
        b"Foo=Power; Expires=Fri, 17 Aug 2018 20:55:04 GMT; Domain=something.org",
    ),
    (
        b"Foo",
        b"Power",
        datetime(2018, 8, 17, 20, 55, 4),
        b"something.org",
        b"/",
        True,
        False,
        None,
        None,
        b"Foo=Power; Expires=Fri, 17 Aug 2018 20:55:04 GMT; Domain=something.org; Path=/; HttpOnly",
    ),
    (
        b"Foo",
        b"Power",
        datetime(2018, 8, 17, 20, 55, 4),
        b"something.org",
        b"/",
        True,
        True,
        None,
        None,
        b"Foo=Power; Expires=Fri, 17 Aug 2018 20:55:04 GMT; Domain=something.org; Path=/; HttpOnly; Secure",
    ),
    (
        b"Foo",
        b"Power",
        datetime(2018, 8, 17, 20, 55, 4),
        b"something.org",
        b"/",
        True,
        True,
        None,
        b"Lax",
        b"Foo=Power; Expires=Fri, 17 Aug 2018 20:55:04 GMT; Domain=something.org; Path=/; HttpOnly; Secure; SameSite=Lax",
    ),
    (
        b"Foo",
        b"Power",
        datetime(2018, 8, 17, 20, 55, 4),
        b"something.org",
        b"/",
        True,
        True,
        datetime(2018, 8, 20, 20, 55, 4),
        b"Strict",
        b"Foo=Power; Expires=Fri, 17 Aug 2018 20:55:04 GMT; Max-Age=Mon, 20 Aug 2018 20:55:04 GMT; "
        b"Domain=something.org; Path=/; HttpOnly; Secure; SameSite=Strict",
    ),
]


@pytest.mark.parametrize(
    "name,value,expires,domain,path,http_only,secure,max_age,same_site,expected_result",
    COOKIES,
)
def test_write_cookie(
    name,
    value,
    expires,
    domain,
    path,
    http_only,
    secure,
    max_age,
    same_site,
    expected_result,
):
    cookie = Cookie(
        name,
        value,
        datetime_to_cookie_format(expires) if expires else None,
        domain,
        path,
        http_only,
        secure,
        datetime_to_cookie_format(max_age) if max_age else None,
        same_site,
    )
    value = scribe.write_response_cookie(cookie)
    assert value == expected_result


@pytest.mark.parametrize(
    "name,value,expires,domain,path,http_only,secure,max_age,same_site,expected_result",
    COOKIES,
)
def test_parse_cookie(
    name,
    value,
    expires,
    domain,
    path,
    http_only,
    secure,
    max_age,
    same_site,
    expected_result,
):
    cookie = parse_cookie(expected_result)
    assert cookie is not None
    assert cookie.name == name
    assert cookie.value == value
    if expires:
        assert cookie.expires is not None
        assert datetime_from_cookie_format(cookie.expires) == expires
    assert cookie.domain == domain
    assert cookie.path == path
    assert cookie.http_only == http_only
    assert cookie.secure == secure
    if max_age:
        assert cookie.max_age is not None
        assert datetime_from_cookie_format(cookie.max_age) == max_age


@pytest.mark.parametrize(
    "value,expected_result",
    [
        [b"Sun, 27-Jan-2019 20:40:54 GMT", datetime(2019, 1, 27, 20, 40, 54)],
        [b"Sun, 27 Jan 2019 20:40:54 GMT", datetime(2019, 1, 27, 20, 40, 54)],
        [b"Wed, 21 Oct 2015 07:28:00 GMT", datetime(2015, 10, 21, 7, 28, 00)],
    ],
)
def test_datetime_from_cookie_format(value, expected_result):
    parsed = datetime_from_cookie_format(value)
    assert parsed == expected_result


@pytest.mark.parametrize(
    "expected_result,value",
    [
        [b"Sun, 27 Jan 2019 20:40:54 GMT", datetime(2019, 1, 27, 20, 40, 54)],
        [b"Wed, 21 Oct 2015 07:28:00 GMT", datetime(2015, 10, 21, 7, 28, 00)],
    ],
)
def test_datetime_from_cookie_format_2(expected_result, value):
    bytes_value = datetime_to_cookie_format(value)
    assert bytes_value == expected_result


@pytest.mark.parametrize(
    "value,expected_name,expected_value,expected_path",
    [
        (
            b"ARRAffinity=c12038089a7sdlkj1237192873; Path=/; HttpOnly; Domain=example.scm.azurewebsites.net",
            b"ARRAffinity",
            b"c12038089a7sdlkj1237192873",
            b"/",
        ),
        (
            b"ARRAffinity=c12038089a7sdlkj1237192873;Path=/;HttpOnly;Domain=example.scm.azurewebsites.net",
            b"ARRAffinity",
            b"c12038089a7sdlkj1237192873",
            b"/",
        ),
        (
            b"1P_JAR=2020-08-23-11; expires=Tue, 22-Sep-2020 11:13:40 GMT; path=/; domain=.google.com; Secure",
            b"1P_JAR",
            b"2020-08-23-11",
            b"/",
        ),
        (
            b"NID=204=0K7PurlER1icDcU_vBBCFWff0gPjtSX3saNz-AXBmkjWGi7RWl_XEeV4uAUuHdX0qsAJbaAhl8E-fZTjwMlTyB9Du_bkal2PHdlnz6h0iKsBNjC5ee8JePM-0PW6hCKdyxyORH6Dzhd7kkvJBhZzk6HQz0QeP8vi9h9eDGL0RGs; expires=Mon, 22-Feb-2021 11:13:40 GMT; path=/; domain=.google.com; HttpOnly",
            b"NID=204",
            b"0K7PurlER1icDcU_vBBCFWff0gPjtSX3saNz-AXBmkjWGi7RWl_XEeV4uAUuHdX0qsAJbaAhl8E-fZTjwMlTyB9Du_bkal2PHdlnz6h0iKsBNjC5ee8JePM-0PW6hCKdyxyORH6Dzhd7kkvJBhZzk6HQz0QeP8vi9h9eDGL0RGs",
            b"/",
        ),
    ],
)
def test_parse_cookie_separators(value, expected_name, expected_value, expected_path):
    cookie = parse_cookie(value)

    assert cookie is not None
    assert cookie.name == expected_name
    assert cookie.value == expected_value
    assert cookie.path == expected_path
