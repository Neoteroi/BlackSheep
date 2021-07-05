import json
from typing import Any

from essentials.json import dumps


def default_json_dumps(obj):
    return dumps(obj, separators=(",", ":"))


class JsonPlugin:
    def __init__(self):
        self._loads = json.loads
        self._dumps = default_json_dumps

    def use(self, loads=json.loads, dumps=json.dumps):
        self._loads = loads
        self._dumps = dumps

    def loads(self, text: str) -> Any:
        return self._loads(text)

    def dumps(self, obj: Any) -> str:
        return self._dumps(obj)
