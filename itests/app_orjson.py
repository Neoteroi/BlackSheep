import base64
import dataclasses
import os
import uuid
from datetime import datetime

import orjson
import uvicorn

from blacksheep.plugins import json as json_plugin
from blacksheep.server import Application
from blacksheep.server.responses import json

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


def orjson_dumps(obj):
    _validate_process_pid()

    def default(x):
        if isinstance(x, bytes):
            return base64.urlsafe_b64encode(x).decode("utf-8")

        raise TypeError

    return orjson.dumps(obj, default=default).decode("utf-8")


def configure_json_settings():
    json_plugin.use(
        loads=orjson.loads,
        dumps=orjson_dumps,
    )


app_orjson = Application(show_error_details=True)


@dataclasses.dataclass
class MyData:
    id: uuid.UUID
    name: str
    data: bytes
    created_at: datetime


@app_orjson.router.post("/echo-posted-json")
async def post_json(request):
    data = await request.json()
    assert data is not None
    return json(data)


@app_orjson.router.get("/get-dict-json")
def get_json():
    return json({"foo": "bar"})


@app_orjson.router.get("/get-dataclass-json")
def get_json_dataclass():
    return json(
        MyData(
            id=uuid.UUID("674fc748-96ac-4cde-8b33-5b76302a8706"),
            name="My UTF8 name is ⌚",
            created_at=datetime(year=2021, month=7, day=5, hour=14, minute=10),
            data=b"test-data",
        )
    )


if __name__ == "__main__":
    configure_json_settings()
    uvicorn.run(app_orjson, host="127.0.0.1", port=44557, log_level="debug")
