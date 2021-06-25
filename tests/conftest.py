import pytest

from blacksheep.testing.messages import MockReceive, MockSend
from tests.utils.application import FakeApplication


@pytest.fixture
def app():
    return FakeApplication()


@pytest.fixture
def mock_send():
    return MockSend()


@pytest.fixture
def mock_receive():
    def decorator(content=None):
        if content is None:
            return MockReceive()
        return MockReceive(content)

    return decorator
