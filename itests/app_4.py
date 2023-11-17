import dataclasses
import json as builtin_json
import os
import uuid
from datetime import datetime

import uvicorn
from openapidocs.v3 import Info

from blacksheep import JSONContent, Response
from blacksheep.server import Application
from blacksheep.server.bindings import FromJSON
from blacksheep.server.compression import use_gzip_compression
from blacksheep.server.openapi.ui import ReDocUIProvider, UIFilesOptions
from blacksheep.server.openapi.v3 import OpenAPIHandler
from blacksheep.server.responses import json
from blacksheep.server.websocket import WebSocket
from blacksheep.settings.json import default_json_dumps, json_settings

from .utils import get_test_files_url

SINGLE_PID = None


def _validate_process_pid():
    # Explanation:
    # since we use global settings for JSON - which makes sense and is legitimate for
    # users of BlackSheep - but we don't want to apply the same JSON settings to the
    # whole test suite (most tests should run using the default JSON settings), we
    # leverage process forking to apply global settings to a specific process.
    # To ensure that the test suite runs with the right JSON settings, here we validate
    # that a single process uses specific JSON settings.
    global SINGLE_PID

    if SINGLE_PID is None:
        SINGLE_PID = os.getpid()
    else:
        assert (
            SINGLE_PID == os.getpid()
        ), "Specific JSON settings were expected to be tested in a single process!"


def custom_dumps(obj):
    _validate_process_pid()

    # apply a transformation here, so we can better assert that this function is
    # used to handle serialization
    if isinstance(obj, dict) and "@" in obj:
        obj["modified_key"] = obj["@"]
        del obj["@"]

    return default_json_dumps(obj)


def custom_loads(value):
    _validate_process_pid()

    obj = builtin_json.loads(value)

    # apply a transformation here, so we can better assert that this function is
    # used to handle deserialization
    if isinstance(obj, dict) and "$" in obj:
        obj["modified_key"] = obj["$"]
        del obj["$"]

    return obj


def configure_json_settings():
    json_settings.use(
        loads=custom_loads,
        dumps=custom_dumps,
    )


app_4 = Application(show_error_details=True)

use_gzip_compression(app_4)


@dataclasses.dataclass
class MyData:
    id: uuid.UUID
    name: str
    data: bytes
    created_at: datetime


@app_4.router.post("/echo-posted-json")
async def post_json(request):
    data = await request.json()
    assert data is not None
    return json(data)


@app_4.router.get("/get-dict-json")
def get_json():
    return json({"foo": "bar"})


@app_4.router.post("/echo-json-using-json-function")
def echo_json_using_function(data: FromJSON[dict]):
    # This also ensures that the json function uses the JSON serializer
    # configured in the JSON settings
    return json(data.value)


@app_4.router.post("/echo-json-using-json-content")
def echo_json_using_content_class(data: FromJSON[dict]):
    # This also ensures that the JSONContent class uses the JSON serializer
    # configured in the JSON settings
    return Response(
        200,
        None,
        JSONContent(data.value),
    )


@app_4.router.get("/get-dataclass-json")
def get_json_dataclass():
    return json(
        MyData(
            id=uuid.UUID("674fc748-96ac-4cde-8b33-5b76302a8706"),
            name="My UTF8 name is ⌚",
            created_at=datetime(year=2021, month=7, day=5, hour=14, minute=10),
            data=b"test-data",
        )
    )


@app_4.router.ws("/websocket-echo-text")
async def echo_text(websocket: WebSocket):
    await websocket.accept()

    while True:
        msg = await websocket.receive_text()
        await websocket.send_text(msg)


@app_4.router.ws("/websocket-echo-bytes")
async def echo_bytes(websocket: WebSocket):
    await websocket.accept()

    while True:
        msg = await websocket.receive_bytes()
        await websocket.send_bytes(msg)


@app_4.router.ws("/websocket-echo-json")
async def echo_json(websocket: WebSocket):
    await websocket.accept()

    while True:
        msg = await websocket.receive_json()
        await websocket.send_json(msg)


docs = OpenAPIHandler(info=Info(title="Cats API", version="0.0.1"))
docs.ui_providers[0].ui_files = UIFilesOptions(
    js_url=get_test_files_url("swag-js"),
    css_url=get_test_files_url("swag-css"),
)
docs.ui_providers.append(
    ReDocUIProvider(
        ui_files=UIFilesOptions(
            js_url=get_test_files_url("redoc-js"),
            fonts_url=get_test_files_url("redoc-fonts"),
        )
    )
)
docs.bind_app(app_4)

if __name__ == "__main__":
    configure_json_settings()
    uvicorn.run(app_4, host="127.0.0.1", port=44557, log_level="debug")
