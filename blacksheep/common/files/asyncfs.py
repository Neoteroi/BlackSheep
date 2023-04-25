from asyncio import AbstractEventLoop
from concurrent.futures.thread import ThreadPoolExecutor
from typing import IO, Any, AnyStr, AsyncIterable, Callable, Optional, Union

from blacksheep.utils.aio import get_running_loop


class PoolClient:
    def __init__(
        self,
        loop: Optional[AbstractEventLoop] = None,
        executor: Optional[ThreadPoolExecutor] = None,
    ):
        self._loop = loop or get_running_loop()
        self._executor = executor

    @property
    def loop(self) -> AbstractEventLoop:
        return self._loop

    async def run(self, func, *args) -> Any:
        return await self._loop.run_in_executor(self._executor, func, *args)


class FileContext(PoolClient):
    def __init__(
        self,
        file_path: str,
        *,
        loop: Optional[AbstractEventLoop] = None,
        mode: str = "rb",
    ):
        super().__init__(loop)
        self._file_path = file_path
        self._file = None
        self._mode = mode

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def file(self) -> IO:
        if self._file is None:
            raise TypeError("The file is not open.")
        return self._file

    async def seek(self, offset: int, whence: int = 0) -> None:
        await self.run(self.file.seek, offset, whence)

    async def read(self, chunk_size: Optional[int] = None) -> bytes:
        return await self.run(self.file.read, chunk_size)

    async def write(
        self, data: Union[AnyStr, Callable[[], AsyncIterable[AnyStr]]]
    ) -> None:
        if isinstance(data, bytes) or isinstance(data, str):
            await self.run(self.file.write, data)
        else:
            async for chunk in data():
                await self.run(self.file.write, chunk)

    async def chunks(self, chunk_size: int = 1024 * 64) -> AsyncIterable[AnyStr]:
        while True:
            chunk = await self.run(self.file.read, chunk_size)

            if not chunk:
                break

            yield chunk
        yield b""

    async def open(self) -> IO:
        return await self.run(open, self._file_path, self._mode)

    async def __aenter__(self):
        self._file = await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            await self.run(self._file.close)
        finally:
            self._file = None


class FilesHandler:
    """Provides methods to handle files asynchronously."""

    def open(
        self, file_path: str, mode: str = "rb", loop: Optional[AbstractEventLoop] = None
    ) -> FileContext:
        return FileContext(file_path, mode=mode, loop=loop)

    async def read(
        self, file_path: str, size: Optional[int] = None, mode: str = "rb"
    ) -> AnyStr:
        async with self.open(file_path, mode=mode) as file:
            return await file.read(size)

    async def write(
        self,
        file_path: str,
        data: Union[AnyStr, Callable[[], AsyncIterable[AnyStr]]],
        mode: str = "wb",
    ) -> None:
        async with self.open(file_path, mode=mode) as file:
            await file.write(data)

    async def chunks(
        self, file_path: str, chunk_size: int = 1024 * 64
    ) -> AsyncIterable[AnyStr]:
        async with self.open(file_path) as file:
            async for chunk in file.chunks(chunk_size):
                yield chunk
