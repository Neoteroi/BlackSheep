import uuid
import base64
import uvicorn
import orjson
import dataclasses
from datetime import datetime

from blacksheep.server import Application
from blacksheep.server.responses import json
from blacksheep.plugins import Plugins, JSONPlugin


def orjson_dumps(obj):
    def default(x):
        if isinstance(x, bytes):
            return base64.urlsafe_b64encode(x).decode('utf-8')

        raise TypeError

    return orjson.dumps(obj, default=default).decode('utf-8')


app_orjson = Application(
    show_error_details=True,
    plugins=Plugins(
        json=JSONPlugin(
            loads=orjson.loads,
            dumps=orjson_dumps,
        )
    )
)


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
    return json(MyData(
        id=uuid.UUID('674fc748-96ac-4cde-8b33-5b76302a8706'),
        name='My UTF8 name is ⌚',
        created_at=datetime(year=2021, month=7, day=5, hour=14, minute=10),
        data=b'test-data',
    ))


if __name__ == "__main__":
    uvicorn.run(app_orjson, host="127.0.0.1", port=44557, log_level="debug")
