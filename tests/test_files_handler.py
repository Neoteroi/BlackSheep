import asyncio
import os
import pathlib
import shutil
from uuid import uuid4

import pytest

from blacksheep.common.files.asyncfs import FileContext, FilesHandler


@pytest.fixture()
def files_folder():
    return pathlib.Path(__file__).parent.absolute() / "files"


@pytest.fixture(scope="module")
def temp_files_folder():
    temp_folder = pathlib.Path(__file__).parent.absolute() / ".out"
    if not temp_folder.exists():
        os.makedirs(temp_folder)
    yield temp_folder
    shutil.rmtree(temp_folder)


@pytest.mark.parametrize(
    "file_name", ["example.txt", "pexels-photo-126407.jpeg", "README.md"]
)
async def test_read_file(files_folder: pathlib.Path, file_name: str):
    handler = FilesHandler()
    full_file_path = str(files_folder / file_name)

    contents = await handler.read(full_file_path)

    with open(full_file_path, mode="rb") as f:
        expected_contents = f.read()

    assert contents == expected_contents


@pytest.mark.parametrize("file_name", ["example.txt", "README.md"])
async def test_read_file_rt_mode(files_folder: pathlib.Path, file_name: str):
    handler = FilesHandler()
    full_file_path = str(files_folder / file_name)

    contents = await handler.read(full_file_path, mode="rt")

    with open(full_file_path, mode="rt") as f:
        expected_contents = f.read()

    assert contents == expected_contents


@pytest.mark.parametrize(
    "file_name", ["example.txt", "pexels-photo-126407.jpeg", "README.md"]
)
async def test_read_file_with_open(files_folder: pathlib.Path, file_name: str):
    handler = FilesHandler()

    full_file_path = str(files_folder / file_name)
    async with handler.open(full_file_path) as file_context:
        contents = await file_context.read()

    with open(full_file_path, mode="rb") as file:
        expected_contents = file.read()

    assert contents == expected_contents


@pytest.mark.parametrize(
    "file_name,index,size",
    [
        ["example.txt", 0, 10],
        ["example.txt", 10, 10],
        ["example.txt", 5, 15],
        ["README.md", 0, 10],
        ["README.md", 10, 10],
        ["README.md", 5, 15],
    ],
)
async def test_seek_and_read_chunk(
    files_folder: pathlib.Path, file_name: str, index: int, size: int
):
    handler = FilesHandler()

    full_file_path = str(files_folder / file_name)
    async with handler.open(full_file_path) as file_context:
        await file_context.seek(index)
        chunk_read_async = await file_context.read(size)

    with open(full_file_path, mode="rb") as file:
        file.seek(index)
        chunk_read = file.read(size)

    assert chunk_read_async == chunk_read


@pytest.mark.parametrize(
    "file_name", ["example.txt", "pexels-photo-126407.jpeg", "README.md"]
)
async def test_read_file_chunks(files_folder: pathlib.Path, file_name: str):
    handler = FilesHandler()
    full_file_path = str(files_folder / file_name)

    chunk: bytes
    chunk_size = 1024
    contents = b""
    expected_contents = b""

    async with handler.open(full_file_path) as file_context:
        async for chunk in file_context.chunks(chunk_size):
            assert chunk is not None
            contents += chunk

    with open(full_file_path, mode="rb") as f:
        while True:
            chunk = f.read(chunk_size)

            if not chunk:
                break
            expected_contents += chunk

    assert contents == expected_contents


async def test_write_file(temp_files_folder: pathlib.Path):
    handler = FilesHandler()
    file_name = str(uuid4()) + ".txt"
    full_file_path = str(temp_files_folder / file_name)

    contents = b"Lorem ipsum dolor sit"
    await handler.write(full_file_path, contents)

    with open(full_file_path, mode="rb") as f:
        expected_contents = f.read()

    assert contents == expected_contents


async def test_write_file_text_mode(temp_files_folder: pathlib.Path):
    handler = FilesHandler()
    file_name = str(uuid4()) + ".txt"
    full_file_path = str(temp_files_folder / file_name)

    contents = "Lorem ipsum dolor sit"
    await handler.write(full_file_path, contents, mode="wt")

    with open(full_file_path, mode="rt") as f:
        expected_contents = f.read()

    assert contents == expected_contents


async def test_write_file_with_iterable(temp_files_folder: pathlib.Path):
    handler = FilesHandler()
    file_name = str(uuid4()) + ".txt"
    full_file_path = str(temp_files_folder / file_name)

    async def provider():
        yield b"Lorem "
        await asyncio.sleep(0.01)
        yield b"ipsum"
        await asyncio.sleep(0.01)
        yield b" dolor"
        yield b" sit"

    await handler.write(full_file_path, provider)

    with open(full_file_path, mode="rb") as f:
        expected_contents = f.read()

    assert b"Lorem ipsum dolor sit" == expected_contents


async def test_file_context_raises_for_invalid_mode():
    handler = FilesHandler()

    with pytest.raises(ValueError) as error_info:
        async with handler.open("foo.txt", mode="xx") as file_context:
            file_context.write("Foo")

    assert "invalid mode" in str(error_info.value)


async def test_file_context_raises_if_file_is_not_open():
    with pytest.raises(TypeError) as error_info:
        file_context = FileContext("foo.txt")
        await file_context.read()

    assert str(error_info.value) == "The file is not open."
