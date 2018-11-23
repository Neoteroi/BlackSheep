import pkg_resources


def get_resource_file_content(file_name):
    with open(pkg_resources.resource_filename(__name__, './res/' + file_name), mode='rt') as source:
        return source.read()
