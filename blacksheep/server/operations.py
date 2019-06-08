from typing import Optional
from guardpost.authentication import Identity


class OperationContext:

    __slots__ = ('identity',)

    def __init__(self):
        self.identity = None  # type: Optional[Identity]

