from os import path

# import pkg_resources
from importlib.resources import files as pkg_resources_files


def get_resource_file_content(file_name: str) -> str:
    with open(
        pkg_resources_files(__name__) / path.join(".", "res", file_name),
        mode="rt",
    ) as source:
        return source.read()
