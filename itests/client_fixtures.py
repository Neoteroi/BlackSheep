import os
import pathlib


def get_static_path(file_name):
    static_folder_path = pathlib.Path(__file__).parent.absolute() / "static"
    return os.path.join(str(static_folder_path), file_name.lstrip("/"))
