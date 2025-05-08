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
    path = str(root_path)
    modules = [
        os.path.basename(f)[:-3]
        for f in glob.glob(path + "/*.py")
        if not os.path.basename(f).startswith("_")
    ]
    stripped_path = os.path.relpath(path).replace("/", ".").replace("\\", ".")
    for module in modules:
        __import__(stripped_path + "." + module)


def clonefunc(func):
    """
    Clone a function, preserving its name and docstring.
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
