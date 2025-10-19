import os

import pytest

from blacksheep.utils.aio import get_running_loop
from itests.client_fixtures import *

os.environ["APP_DEFAULT_ROUTER"] = "false"


# async is needed here, to use the same event loop
@pytest.fixture(scope="session")
async def event_loop():
    loop = get_running_loop()
    yield loop
    # pytest-asyncio closes the loop and would complain if the loop was closed here.
