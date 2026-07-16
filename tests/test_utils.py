import sys
from typing import AnyStr, Sequence

import pytest

from blacksheep.utils import ensure_bytes, ensure_str, join_fragments
from blacksheep.utils.meta import import_child_modules


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


def test_import_child_modules_independent_of_cwd(tmp_path, monkeypatch):
    """
    import_child_modules must resolve the dotted module path of a package
    folder from its own location on disk, not from the current working
    directory of the process. This reproduces the crash reported when a
    blacksheep app is installed as a package (e.g. with `uv tool install`)
    and started from an unrelated working directory: os.getcwd()-based
    relative paths produced bogus dotted paths such as ".local.share...",
    raising ModuleNotFoundError.
    """
    package_root = tmp_path / "myapp_pkg"
    package = package_root / "myapp"
    routes_folder = package / "routes"
    routes_folder.mkdir(parents=True)

    (package / "__init__.py").write_text("")
    (routes_folder / "__init__.py").write_text("")
    (routes_folder / "home.py").write_text("imported = True\n")

    unrelated_cwd = tmp_path / "somewhere_else"
    unrelated_cwd.mkdir()

    monkeypatch.chdir(unrelated_cwd)
    monkeypatch.syspath_prepend(str(package_root))

    try:
        import_child_modules(routes_folder)
        assert "myapp.routes.home" in sys.modules
        assert sys.modules["myapp.routes.home"].imported is True
    finally:
        for name in list(sys.modules):
            if name == "myapp" or name.startswith("myapp."):
                del sys.modules[name]
