import os
from email.utils import formatdate

from .pathsutils import get_mime_type_from_name


class FileInfo:
    __slots__ = ("etag", "size", "mime", "modified_time")

    def __init__(self, size: int, etag: str, mime: str, modified_time: str):
        self.size = size
        self.etag = etag
        self.mime = mime
        self.modified_time = modified_time

    def __repr__(self):
        return (
            f"<FileInfo mime={self.mime} "
            f"etag={self.etag} "
            f"modified_time={self.modified_time}>"
        )

    def to_dict(self):
        return {key: getattr(self, key, None) for key in FileInfo.__slots__}

    @classmethod
    def from_path(cls, resource_path: str):
        stat = os.stat(resource_path)
        return cls(
            stat.st_size,
            str(stat.st_mtime),
            get_mime_type_from_name(resource_path),
            formatdate(stat.st_mtime, usegmt=True),
        )
