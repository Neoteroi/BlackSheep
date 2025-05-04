"""
Benchmarks testing functions used to write response bytes.
"""

from pathlib import Path

from blacksheep.contents import TextContent
from blacksheep.messages import Response
from blacksheep.scribe import write_response
from perf.benchmarks import async_benchmark, main_run

ITERATIONS = 10000

LOREM_IPSUM = (Path(__file__).parent / "res" / "lorem.txt").read_text(encoding="utf-8")
RESPONSE_HEADERS = [
    (b"Content-Type", b"text/html; charset=utf-8"),
    (b"Content-Length", b"123"),
    (b"Connection", b"keep-alive"),
    (b"Cache-Control", b"no-cache, no-store, must-revalidate"),
    (b"Pragma", b"no-cache"),
    (b"Expires", b"0"),
    (b"X-Frame-Options", b"DENY"),
    (b"X-Content-Type-Options", b"nosniff"),
    (b"X-XSS-Protection", b"1; mode=block"),
    (b"Strict-Transport-Security", b"max-age=31536000; includeSubDomains"),
    (b"Server", b"BlackSheep/1.0"),
]


async def test_write_text_response():
    response = Response(200, RESPONSE_HEADERS).with_content(TextContent(LOREM_IPSUM))
    data = bytearray()
    async for chunk in write_response(response):
        data.extend(chunk)
    return data


async def test_write_small_response():
    response = Response(404, RESPONSE_HEADERS).with_content(TextContent("Not Found"))
    data = bytearray()
    async for chunk in write_response(response):
        data.extend(chunk)
    return data


async def benchmark_write_small_response(iterations=ITERATIONS):
    return await async_benchmark(test_write_small_response, iterations)


async def benchmark_write_text_response(iterations=ITERATIONS):
    return await async_benchmark(test_write_text_response, iterations)


async def main():
    await benchmark_write_text_response(ITERATIONS)
    await benchmark_write_small_response(ITERATIONS)


if __name__ == "__main__":
    main_run(main)
