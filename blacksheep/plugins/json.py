import json
from typing import Any, Callable, Union

from essentials.json import dumps


def default_json_dumps(obj):
    return dumps(obj, separators=(",", ":"))


LoadsFunc = Callable[[Union[str, bytes]], Any]
DumpsFunc = Callable[[Any], str]


class JSONPlugin:
    def __init__(
        self,
        loads: LoadsFunc = json.loads,
        dumps: DumpsFunc = default_json_dumps,
    ):
        self._loads = loads
        self._dumps = dumps

    def loads(self, text: str) -> Any:
        return self._loads(text)

    def dumps(self, obj: Any) -> str:
        return self._dumps(obj)
