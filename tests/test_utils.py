from typing import AnyStr, Sequence

import pytest

from blacksheep.utils import ensure_bytes, ensure_str, join_fragments


@pytest.mark.parametrize(
    "fragments,expected_value",
    [
        [["a"], "/a"],
        [["a", "b", "c", "d"], "/a/b/c/d"],
        [["a", None, "b", "c", "", "d"], "/a/b/c/d"],
        [[b"a", b"b", b"c", b"d"], "/a/b/c/d"],
        [[b"a", "b", "c", b"d"], "/a/b/c/d"],
        [["hello/world", "today"], "/hello/world/today"],
        [[b"hello/world", b"today"], "/hello/world/today"],
        [["//hello///world", "/today/"], "/hello/world/today"],
    ],
)
def test_join_url_fragments(fragments: Sequence[AnyStr], expected_value: str):
    joined = join_fragments(*fragments)
    assert joined == expected_value


@pytest.mark.parametrize(
    "value,expected_result", [("hello", b"hello"), (b"hello", b"hello")]
)
def test_ensure_bytes(value, expected_result):
    assert ensure_bytes(value) == expected_result


@pytest.mark.parametrize(
    "value,expected_result", [("hello", "hello"), (b"hello", "hello")]
)
def test_ensure_str(value, expected_result):
    assert ensure_str(value) == expected_result


def test_ensure_bytes_throws_for_invalid_value():
    with pytest.raises(ValueError):
        ensure_bytes(True)  # type: ignore


def test_ensure_str_throws_for_invalid_value():
    with pytest.raises(ValueError):
        ensure_str(True)  # type: ignore
