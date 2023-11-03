from importlib.resources import files


def get_resource_file_path(anchor, file_name: str) -> str:
    return str(files(anchor) / file_name)


def get_resource_file_content(file_name: str) -> str:
    with open(
        get_resource_file_path("blacksheep.server.res", file_name),
        mode="rt",
    ) as source:
        return source.read()
