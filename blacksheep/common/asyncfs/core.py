import asyncio
from asyncio import BaseEventLoop
from typing import AsyncIterable, Optional
from concurrent.futures.thread import ThreadPoolExecutor


class PoolClient:

    def __init__(
        self,
        loop: Optional[BaseEventLoop] = None,
        executor: Optional[ThreadPoolExecutor] = None
    ):
        self._loop = loop or asyncio.get_event_loop()
        self._executor = executor

    async def run(self, func, *args):
        return await self._loop.run_in_executor(self._executor, func, *args)


class FileContext(PoolClient):

    def __init__(
        self,
        file_path: str,
        loop: Optional[BaseEventLoop] = None
    ):
        super().__init__(loop)
        self._file_path = file_path
        self._file = None

    async def __aenter__(self):
        self._file = await self.run(open, self._file_path, 'rb')
        return self._file

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            await self.run(self._file.close)
        finally:
            self._file = None


class FilesReader(PoolClient):
    """Provides methods to read files bytes asynchronously."""

    def __init__(self, loop: Optional[BaseEventLoop] = None):
        super().__init__(loop)

    async def read(
        self,
        file_path: str,
        size: Optional[int] = None
    ) -> bytes:
        async with FileContext(file_path) as file:
            return await self.run(file.read, size)

    async def chunks(
        self,
        file_path: str,
        chunk_size: int = 1024*64
    ) -> AsyncIterable[bytes]:
        async with FileContext(file_path) as file:
            while True:
                chunk = await self.run(file.read, chunk_size)

                if not chunk:
                    yield b''
                    break

                yield chunk
