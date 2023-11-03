from os import path

# import pkg_resources
try:
    from importlib.resources import files as pkg_resources_files

    def get_resource_file_path(anchor, resource_name: str) -> str:
        return str(pkg_resources_files(anchor) / resource_name)

    def get_resource_file_content(file_name: str) -> str:
        with open(
            get_resource_file_path(__name__, path.join(".", "res", file_name)),
            mode="rt",
        ) as source:
            return source.read()

except ImportError:
    # import pkg_resources
    from pkg_resources import resource_filename

    def get_resource_file_path(anchor, resource_name: str) -> str:
        return resource_filename(anchor, resource_name)

    def get_resource_file_content(file_name: str) -> str:
        with open(
            get_resource_file_path(__name__, path.join(".", "res", file_name)),
            mode="rt",
        ) as source:
            return source.read()
