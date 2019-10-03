from blacksheep.messages import Request


def get_status_line(status: int) -> bytes: ...

def is_small_request(request: Request) -> bool: ...

def request_has_body(request: Request) -> bool: ...

def write_small_request(request: Request) -> bytes: ...

def write_request_without_body(request: Request) -> bytes: ...
