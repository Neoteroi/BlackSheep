import uuid
import uvicorn
import orjson
import dataclasses
from datetime import datetime

from blacksheep.server import Application
from blacksheep.server.responses import json
from blacksheep.plugins import json as json_plugin

json_plugin.use(
    loads=orjson.loads,
    dumps=lambda x: orjson.dumps(x).decode('utf-8'),
)

app_orjson = Application(show_error_details=True)


@dataclasses.dataclass
class MyData:
    id: uuid.UUID
    name: str
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
    ))


if __name__ == "__main__":
    uvicorn.run(app_orjson, host="127.0.0.1", port=44557, log_level="debug")
