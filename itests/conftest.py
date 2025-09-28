import asyncio
import os

import pytest

from itests.client_fixtures import *

os.environ["APP_DEFAULT_ROUTER"] = "false"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    # pytest-asyncio closes the loop and would complain if the loop was closed here.
