from datetime import datetime

import pytest

from blacksheep import (
    Cookie,
    CookieSameSiteMode,
    datetime_from_cookie_format,
    datetime_to_cookie_format,
    parse_cookie,
    scribe,
)
from blacksheep.cookies import CookieValueExceedsMaximumLength

COOKIES = [
    (
        "Foo",
        "Power",
        None,
        None,
        None,
        False,
        False,
        -1,
        CookieSameSiteMode.UNDEFINED,
        b"Foo=Power",
    ),
    (
        "Foo",
        "Hello World;",
        None,
        None,
        None,
        False,
        False,
        -1,
        CookieSameSiteMode.UNDEFINED,
        b"Foo=Hello%20World%3B",
    ),
    (
        "Foo; foo",
        "Hello World;",
        None,
        None,
        None,
        False,
        False,
        -1,
        CookieSameSiteMode.UNDEFINED,
        b"Foo%3B%20foo=Hello%20World%3B",
    ),
    (
        "Foo",
        "Power",
        datetime(2018, 8, 17, 20, 55, 4),
        None,
        None,
        False,
        False,
        -1,
        CookieSameSiteMode.UNDEFINED,
        b"Foo=Power; Expires=Fri, 17 Aug 2018 20:55:04 GMT",
    ),
    (
        "Foo",
        "Power",
        datetime(2018, 8, 17, 20, 55, 4),
        "something.org",
        None,
        False,
        False,
        -1,
        CookieSameSiteMode.UNDEFINED,
        b"Foo=Power; Expires=Fri, 17 Aug 2018 20:55:04 GMT; Domain=something.org",
    ),
    (
        "Foo",
        "Power",
        datetime(2018, 8, 17, 20, 55, 4),
        "something.org",
        "/",
        True,
        False,
        -1,
        CookieSameSiteMode.UNDEFINED,
        b"Foo=Power; Expires=Fri, 17 Aug 2018 20:55:04 GMT; Domain=something.org; Path=/; HttpOnly",
    ),
    (
        "Foo",
        "Power",
        datetime(2018, 8, 17, 20, 55, 4),
        "something.org",
        "/",
        True,
        True,
        -1,
        CookieSameSiteMode.UNDEFINED,
        b"Foo=Power; Expires=Fri, 17 Aug 2018 20:55:04 GMT; Domain=something.org; Path=/; HttpOnly; Secure",
    ),
    (
        "Foo",
        "Power",
        datetime(2018, 8, 17, 20, 55, 4),
        "something.org",
        "/",
        True,
        True,
        -1,
        CookieSameSiteMode.LAX,
        b"Foo=Power; Expires=Fri, 17 Aug 2018 20:55:04 GMT; Domain=something.org; Path=/; HttpOnly; Secure; SameSite=Lax",
    ),
    (
        "Foo",
        "Power",
        datetime(2018, 8, 17, 20, 55, 4),
        "something.org",
        "/",
        True,
        True,
        200,
        CookieSameSiteMode.STRICT,
        b"Foo=Power; Expires=Fri, 17 Aug 2018 20:55:04 GMT; Max-Age=200; "
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
        expires,
        domain,
        path,
        http_only,
        secure,
        max_age,
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
        assert cookie.expires == expires
    assert cookie.domain == domain
    assert cookie.path == path
    assert cookie.http_only == http_only
    assert cookie.secure == secure
    if max_age is not None:
        assert cookie.max_age == max_age


@pytest.mark.parametrize(
    "value,expected_result",
    [
        [b"Sun, 27-Jan-2019 20:40:54 GMT", datetime(2019, 1, 27, 20, 40, 54)],
        [b"Sun, 27 Jan 2019 20:40:54 GMT", datetime(2019, 1, 27, 20, 40, 54)],
        [b"Wed, 21 Oct 2015 07:28:00 GMT", datetime(2015, 10, 21, 7, 28, 00)],
        [b"Thu, 31-Dec-37 23:55:55 GMT", datetime(2037, 12, 31, 23, 55, 55)],
        [b"Tuesday, 08-Feb-94 14:15:29 GMT", datetime(1994, 2, 8, 14, 15, 29)],
        [b"09 Feb 1994 22:23:32 GMT", datetime(1994, 2, 9, 22, 23, 32)],
        [b"08-Feb-94 14:15:29 GMT", datetime(1994, 2, 8, 14, 15, 29)],
        [b"08-Feb-1994 14:15:29 GMT", datetime(1994, 2, 8, 14, 15, 29)],
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
def test_datetime_to_cookie_format(expected_result, value):
    bytes_value = datetime_to_cookie_format(value)
    assert bytes_value == expected_result


@pytest.mark.parametrize(
    "value,expected_name,expected_value,expected_path",
    [
        (
            b"ARRAffinity=c12038089a7sdlkj1237192873; Path=/; HttpOnly; Domain=example.scm.azurewebsites.net",
            "ARRAffinity",
            "c12038089a7sdlkj1237192873",
            "/",
        ),
        (
            b"ARRAffinity=c12038089a7sdlkj1237192873;Path=/;HttpOnly;Domain=example.scm.azurewebsites.net",
            "ARRAffinity",
            "c12038089a7sdlkj1237192873",
            "/",
        ),
        (
            b"1P_JAR=2020-08-23-11; expires=Tue, 22-Sep-2020 11:13:40 GMT; path=/; domain=.google.com; Secure",
            "1P_JAR",
            "2020-08-23-11",
            "/",
        ),
        (
            b"NID=204=0K7PurlER1icDcU_vBBCFWff0gPjtSX3saNz-AXBmkjWGi7RWl_XEeV4uAUuHdX0qsAJbaAhl8E-fZTjwMlTyB9Du_bkal2PHdlnz6h0iKsBNjC5ee8JePM-0PW6hCKdyxyORH6Dzhd7kkvJBhZzk6HQz0QeP8vi9h9eDGL0RGs; expires=Mon, 22-Feb-2021 11:13:40 GMT; path=/; domain=.google.com; HttpOnly",
            "NID",
            "204=0K7PurlER1icDcU_vBBCFWff0gPjtSX3saNz-AXBmkjWGi7RWl_XEeV4uAUuHdX0qsAJbaAhl8E-fZTjwMlTyB9Du_bkal2PHdlnz6h0iKsBNjC5ee8JePM-0PW6hCKdyxyORH6Dzhd7kkvJBhZzk6HQz0QeP8vi9h9eDGL0RGs",
            "/",
        ),
        (
            b"session=gAAAAABgVeIWAXQ5iCbIgXThcx9IFORha534yIqw2ZjnqiTKIw7xBcnk-Tc8pvuTpLEuFSv3NRJkr83WBdhc0dpjZrEGBUNCFV8YK17hka43KanCxW5FMhrP00AxvGYyKZ2-vy4CEUIcsN92JAvV763u_ZCZzSpraw==",
            "session",
            "gAAAAABgVeIWAXQ5iCbIgXThcx9IFORha534yIqw2ZjnqiTKIw7xBcnk-Tc8pvuTpLEuFSv3NRJkr83WBdhc0dpjZrEGBUNCFV8YK17hka43KanCxW5FMhrP00AxvGYyKZ2-vy4CEUIcsN92JAvV763u_ZCZzSpraw==",
            None,
        ),
    ],
)
def test_parse_cookie_separators(value, expected_name, expected_value, expected_path):
    cookie = parse_cookie(value)

    assert cookie is not None
    assert cookie.name == expected_name
    assert cookie.value == expected_value
    assert cookie.path == expected_path


def test_raise_for_value_exceeding_length():
    with pytest.raises(CookieValueExceedsMaximumLength):
        Cookie("crash", "A" * 4967)

    with pytest.raises(CookieValueExceedsMaximumLength):
        Cookie("crash", "A" * 5000)
