from typing import Optional
from blacksheep.plugins.json import JSONPlugin


class Plugins:
    def __init__(self, json: Optional[JSONPlugin] = None):
        self.json = json or JSONPlugin()
