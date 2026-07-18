import copy
import glob
import inspect
import os
from pathlib import Path


def get_parent_file():
    """
    Returns __file__ of the caller's parent module.
    """
    try:
        return inspect.stack()[2][1]
    except IndexError:
        return ""


def import_child_modules(root_path: Path):
    """
    Import automatically all modules defined
    under a certain package path.
    """
    root_path = root_path.resolve()
    modules = [
        os.path.basename(f)[:-3]
        for f in glob.glob(str(root_path / "*.py"))
        if not os.path.basename(f).startswith("_")
    ]
    # Determine the dotted module path by walking up the directory tree
    # following __init__.py markers, instead of using os.path.relpath
    # (which depends on the current working directory and produces
    # incorrect paths when the app is installed as a package, e.g. via uv tool).
    package_parts: list[str] = []
    current = root_path
    while True:
        if (current / "__init__.py").exists():
            package_parts.append(current.name)
            parent = current.parent
            if parent == current:  # reached filesystem root
                break
            current = parent
        else:
            break
    package_parts.reverse()
    base_package = ".".join(package_parts)
    for module in modules:
        if base_package:
            __import__(base_package + "." + module)
        else:
            __import__(module)


def clonefunc(func):
    """
    Clone a function, preserving its name, docstring, annotations and kwdefaults.
    """
    new_func = func.__class__(
        func.__code__,
        func.__globals__,
        func.__name__,
        func.__defaults__,
        func.__closure__,
    )
    new_func.__doc__ = func.__doc__
    new_func.__dict__ = copy.deepcopy(func.__dict__)
    new_func.__annotations__ = copy.deepcopy(func.__annotations__)
    if func.__kwdefaults__:
        new_func.__kwdefaults__ = copy.deepcopy(func.__kwdefaults__)
    return new_func


def all_subclasses(cls):
    """
    Return all subclasses of a class, including those defined in other modules.
    """
    subclasses = set()
    for subclass in cls.__subclasses__():
        subclasses.add(subclass)
        subclasses.update(all_subclasses(subclass))
    return subclasses
