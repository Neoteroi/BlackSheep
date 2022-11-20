import json
from typing import Any

from essentials.json import dumps


def default_json_dumps(obj):
    return dumps(obj, separators=(",", ":"))


def default_pretty_json_dumps(obj):
    return dumps(obj, indent=4)


class JSONSettings:
    def __init__(self):
        self._loads = json.loads
        self._dumps = default_json_dumps
        self._pretty_dumps = default_pretty_json_dumps

    def use(
        self,
        loads=json.loads,
        dumps=default_json_dumps,
        pretty_dumps=default_pretty_json_dumps,
    ):
        self._loads = loads
        self._dumps = dumps
        self._pretty_dumps = pretty_dumps

    def loads(self, text: str) -> Any:
        return self._loads(text)

    def dumps(self, obj: Any) -> str:
        return self._dumps(obj)

    def pretty_dumps(self, obj: Any) -> str:
        return self._pretty_dumps(obj)


json_settings = JSONSettings()
