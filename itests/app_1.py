import asyncio
import io
import os
import pathlib

import uvicorn

from blacksheep import (
    Application,
    Content,
    ContentDispositionType,
    Cookie,
    FromQuery,
    Request,
    Response,
    file,
    json,
    text,
)
from blacksheep.contents import ASGIContent
from blacksheep.server.compression import use_gzip_compression
from itests.utils import CrashTest, ensure_folder

app = Application(show_error_details=True)

use_gzip_compression(app)

static_folder_path = pathlib.Path(__file__).parent.absolute() / "static"


def get_static_path(file_name):
    static_folder_path = pathlib.Path(__file__).parent.absolute() / "static"
    return os.path.join(str(static_folder_path), file_name)


app.serve_files(static_folder_path, discovery=True)


@app.router.route("/hello-world")
async def hello_world():
    return text("Hello, World!")


@app.router.route("/plain-json")
async def plain_json():
    return json({"message": "Hello, World!"})


@app.router.route("/plain-json-error-simulation")
async def plain_json_error_simulation():
    return json({"message": "Hello, World!"}, status=500)


@app.router.head("/echo-headers")
async def echo_headers(request):
    response = Response(200)

    for header in request.headers:
        response.add_header(header[0], header[1])

    return response


@app.router.route("/echo-cookies")
async def echo_cookies(request):
    cookies = request.cookies
    return json(cookies)


@app.router.route("/set-cookie")
async def set_cookies(name: FromQuery[str], value: FromQuery[str]):
    response = text("Setting cookie")
    response.set_cookie(Cookie(name.value, value.value))
    return response


@app.router.post("/echo-posted-json")
async def post_json(request):
    data = await request.json()
    assert data is not None
    return json(data)


@app.router.post("/echo-posted-form")
async def post_form(request):
    data = await request.form()
    assert data is not None
    return json(data)


@app.router.post("/upload-files")
async def upload_files(request: Request):
    files = await request.files()

    assert bool(files)

    folder = "out"

    ensure_folder(folder)

    for part in files:
        with open(f"./{folder}/{part.file_name.decode()}", mode="wb") as saved_filed:
            saved_filed.write(part.data)

    return json(
        {
            "folder": folder,
            "files": [{"name": file.file_name.decode()} for file in files],
        }
    )


@app.router.get("/echo-query")
async def echo_query(request: Request):
    params = request.query
    return json(params)


@app.router.get("/echo-route/:one/:two/:three")
async def echo_route_values(request: Request):
    params = request.route_values
    return json(params)


@app.router.get("/echo-route-autobind/:one/:two/:three")
async def echo_route_values_autobind(one, two, three):
    return json(dict(one=one, two=two, three=three))


@app.router.route("/crash")
async def crash():
    raise CrashTest()


class Item:
    def __init__(self, name, power):
        self.name = name
        self.power = power


@app.router.route("/echo-posted-json-autobind", methods=["POST"])
async def upload_item(request, item: Item):
    assert request is not None
    assert item is not None
    return json(item.__dict__)


@app.router.post("/echo-chunked-text")
async def echo_chunked_text(request):
    text_from_client = await request.text()
    return text(text_from_client)


@app.router.post("/echo-streamed-text")
async def echo_streamed_test(request):
    async def echo():
        async for chunk in request.stream():
            yield chunk

    return Response(200, content=Content(b"text/plain; charset=utf-8", echo))


@app.router.get("/file-response-with-path")
async def send_file_with_async_gen():
    return file(
        get_static_path("pexels-photo-923360.jpeg"),
        "image/jpeg",
        file_name="nice-cat.jpg",
        content_disposition=ContentDispositionType.INLINE,
    )


@app.router.get("/file-response-with-generator")
async def send_file_with_async_gen_two():
    async def generator():
        yield b"Black Knight: None shall pass.\n"
        yield b"King Arthur: What?\n"
        yield b"Black Knight: None shall pass.\n"
        await asyncio.sleep(0.01)
        yield (
            b"King Arthur: I have no quarrel with you, good Sir Knight, "
            b"but I must cross this bridge.\n"
        )
        yield b"Black Knight: Then you shall die.\n"
        yield b"King Arthur: I command you, as King of the Britons, to stand aside!\n"
        await asyncio.sleep(0.01)
        yield b"Black Knight: I move for no man.\n"
        yield b"King Arthur: So be it!\n"
        yield (
            b"[rounds of melee, with Arthur cutting off the left arm of "
            b"the black knight.]\n"
        )
        await asyncio.sleep(0.01)
        yield b"King Arthur: Now stand aside, worthy adversary.\n"
        yield b"Black Knight: Tis but a scratch.\n"

    return file(
        generator,
        "text/plain",
        file_name="black-knight.txt",
        content_disposition=ContentDispositionType.INLINE,
    )


@app.router.get("/file-response-with-bytes")
async def send_file_with_bytes():
    def generator():
        yield b"Black Knight: None shall pass.\n"
        yield b"King Arthur: What?\n"
        yield b"Black Knight: None shall pass.\n"
        yield (
            b"King Arthur: I have no quarrel with you, good Sir Knight, "
            b"but I must cross this bridge.\n"
        )
        yield b"Black Knight: Then you shall die.\n"
        yield b"King Arthur: I command you, as King of the Britons, to stand aside!\n"
        yield b"Black Knight: I move for no man.\n"
        yield b"King Arthur: So be it!\n"
        yield (
            b"[rounds of melee, with Arthur cutting off the left arm of "
            b"the black knight.]\n"
        )
        yield b"King Arthur: Now stand aside, worthy adversary.\n"
        yield b"Black Knight: Tis but a scratch.\n"

    all_bytes = b"".join(generator())

    return file(
        all_bytes,
        "text/plain",
        file_name="black-knight.txt",
        content_disposition=ContentDispositionType.INLINE,
    )


@app.router.get("/file-response-with-bytesio")
async def send_file_with_bytes_io():
    return file(
        io.BytesIO(b"some initial binary data: "),
        "text/plain",
        file_name="data.txt",
        content_disposition=ContentDispositionType.INLINE,
    )


@app.router.get("/check-disconnected")
async def check_disconnected(request: Request, expect_disconnected: bool):
    check_file = pathlib.Path(".is-disconnected.txt")
    assert await request.is_disconnected() is False
    # Simulate a delay
    await asyncio.sleep(0.3)

    if expect_disconnected:
        # Testing the scenario when the client disconnected
        assert (
            await request.is_disconnected()
        ), "The client disconnected and this should be visible"
        check_file.write_text("The connection was disconnected")
    else:
        assert (
            await request.is_disconnected() is False
        ), "The client did not disconnect and this should be visible"

    return "OK"


@app.router.get("/read-asgi-receive")
def check_asgi_receive_readable(request: Request):
    content = request.content
    assert isinstance(content, ASGIContent)

    receive = content.receive
    assert callable(receive)

    return "OK"


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=44567, log_level="debug")
