from os import path

import pkg_resources


def get_resource_file_content(file_name: str) -> str:
    with open(
        pkg_resources.resource_filename(__name__, path.join(".", "res", file_name)),
        mode="rt",
    ) as source:
        return source.read()
