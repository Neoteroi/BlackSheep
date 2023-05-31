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
