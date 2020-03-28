from abc import abstractmethod, ABC


class FileSystemHandler(ABC):

    @abstractmethod
    async def read(
        self,
        file_path: str,
        size: Optional[int] = None
    ) -> bytes:
        ...

    @abstractmethod
    async def chunks(
        self,
        file_path: str,
        chunk_size: int = 1024*64
    ) -> AsyncIterable[bytes]:
        ...
